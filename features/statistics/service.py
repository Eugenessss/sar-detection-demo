"""
[Statistics 도메인 - 서비스]
시작일·기간 필터로 조회 범위를 계산하고, 탐지 통계를 화면이 바로 그릴 수 있는
표(DataFrame)·그래프용 피벗으로 가공하는 순수 파이썬 함수.
흐름: resolve_range(범위 계산) → repository.fetch_detection_stats(조회) → pivot_time_series/build_yearly_overlay(그래프 가공).
지역(region_name) 목록은 list_regions로 따로 조회해 화면의 위치 선택 팝오버에 쓴다.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from features.statistics.repository import (
    fetch_detection_stats,
    fetch_equipment_classes,
    fetch_latest_captured_time,
    fetch_latest_captured_time_by_region,
    fetch_regions,
)

# 화면에 노출할 기간 선택지와 실제 timedelta 매핑 (선택 버튼 라벨 = 이 딕셔너리 키).
# 24시간·1년을 맨 앞에 두어 버튼 순서 맨 앞에 오게 한다.
INTERVALS: Dict[str, timedelta] = {
    "24시간": timedelta(hours=24),
    "1년": timedelta(days=365),
    "12시간": timedelta(hours=12),
    "1주": timedelta(weeks=1),
    "1개월": timedelta(days=30),
}

# 기간 선택 버튼 중 부드러운 빨간색으로 강조할 라벨 (24시간·1년).
HIGHLIGHTED_INTERVALS = ("24시간", "1년")

DEFAULT_INTERVAL = "1주"

# 장비 선택 위 위협등급 체크박스에 쓸 등급 목록 (equipment.threat_level 값).
THREAT_LEVELS: List[int] = [1, 2, 3]


@dataclass
class StatisticsResult:
    """통계 화면이 그대로 그릴 수 있는 형태로 담은 결과."""
    start: datetime
    end: datetime
    raw: pd.DataFrame   # 원본 조회 결과 (지역 필터링·표 표시에 함께 쓰인다)


def latest_captured_time() -> Optional[datetime]:
    """DB에 저장된 가장 최근 촬영시각을 돌려준다 (없으면 None).

    분석 현황의 24시간 그래프가 '지금 기준 24시간'에 데이터가 없을 때,
    마지막 촬영 시점 기준 창으로 대신 보여주는 fallback에 쓴다.
    """
    return fetch_latest_captured_time()


def latest_captured_time_by_region() -> Dict[str, datetime]:
    """지역별 마지막 촬영시각을 {region_name: captured_time}으로 돌려준다.

    분석 현황의 지역별 24시간 추이가 지역마다 자기 최신 촬영 시점 기준으로 창을
    잡을 때 쓴다 (지역 간 촬영 주기가 어긋나도 각 지역이 항상 그려지도록)."""
    return fetch_latest_captured_time_by_region()


def resolve_range(start: datetime, interval_label: str) -> Tuple[datetime, datetime]:
    """시작 일시와 기간 라벨로 (시작시각, 종료시각)을 계산한다."""
    end = start + INTERVALS[interval_label]
    return start, end


def build_statistics(start: datetime, end: datetime) -> Optional[StatisticsResult]:
    """기간 내 탐지 통계를 조회해 화면용 원본 표로 가공한다 (조회 결과 없으면 None)."""
    rows = fetch_detection_stats(start, end)
    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["captured_time"] = pd.to_datetime(df["captured_time"])
    df["detected_count"] = pd.to_numeric(df["detected_count"], errors="coerce")

    return StatisticsResult(start=start, end=end, raw=df)


def _drop_all_zero_columns(pivot: pd.DataFrame) -> pd.DataFrame:
    """값이 전부 0인 장비(열)는 그래프에 표시하지 않도록 뺀다."""
    return pivot.loc[:, (pivot != 0).any(axis=0)]


def pivot_time_series(
    df: pd.DataFrame,
    region: Optional[str] = None,
    equipment: Optional[List[str]] = None,
) -> pd.DataFrame:
    """촬영시각 x 장비명 피벗(선 그래프용)을 만든다. region이 주어지면 그 지역만, equipment가 주어지면 그 장비들만,
    값이 전부 0인 장비는 결과에서 뺀다."""
    if region:
        df = df[df["region_name"] == region]
    if equipment is not None:
        df = df[df["class_name"].isin(equipment)]
    pivot = df.pivot_table(
        index="captured_time", columns="class_name", values="detected_count", aggfunc="sum"
    ).fillna(0)
    return _drop_all_zero_columns(pivot)


def _overlay_actual_vs_average(
    df: pd.DataFrame,
    bucket_key: pd.Series,
    bucket_timestamp: Callable[[object], pd.Timestamp],
) -> pd.DataFrame:
    """실제 값과 bucket_key로 묶은 구간 평균값을 한 장문형(tidy) 표로 합친다 (구분: "실제"/"평균").
    bucket_timestamp(구간 키)로 평균 행의 대표 시각을 계산하고, 값이 전부 0인 장비는 뺀다.
    build_yearly_overlay(월 단위)·build_two_hour_overlay(2시간 단위)가 함께 쓴다."""
    actual = df[["captured_time", "class_name", "detected_count"]].copy()
    actual["series"] = "실제"

    average = (
        df.assign(_bucket=bucket_key)
        .groupby(["_bucket", "class_name"], as_index=False)["detected_count"]
        .mean()
    )
    average["captured_time"] = average["_bucket"].apply(bucket_timestamp)
    average["series"] = "평균"
    average = average[["captured_time", "class_name", "detected_count", "series"]]

    has_nonzero = actual.groupby("class_name")["detected_count"].apply(lambda s: (s != 0).any())
    nonzero_classes = has_nonzero[has_nonzero].index

    combined = pd.concat([actual, average], ignore_index=True)
    return combined[combined["class_name"].isin(nonzero_classes)]


def build_yearly_overlay(
    df: pd.DataFrame,
    year: int,
    region: Optional[str] = None,
    equipment: Optional[List[str]] = None,
) -> pd.DataFrame:
    """조회 기간이 "1년"일 때만 쓰는 장문형(tidy) 데이터: 실제 탐지 추이와 반월(보름) 단위 평균을
    한 그래프에 겹쳐 그릴 수 있도록 (촬영시각, 장비명, 탐지수, 구분) 행으로 만든다.
    한 달을 1~15일(전반)/16일~월말(후반) 두 구간으로 나눠 평균을 내
    구분 값은 "실제"(원본 시점별) / "평균"(전반은 8일, 후반은 23일 대표값)이고, 값이 전부 0인 장비는 뺀다."""
    if region:
        df = df[df["region_name"] == region]
    if equipment is not None:
        df = df[df["class_name"].isin(equipment)]
    df = df[df["captured_time"].dt.year == year]

    is_second_half = (df["captured_time"].dt.day > 15).astype(int)
    bucket_key = (df["captured_time"].dt.month - 1) * 2 + is_second_half

    def half_month_timestamp(bucket: int) -> pd.Timestamp:
        month = bucket // 2 + 1
        day = 23 if bucket % 2 else 8
        return pd.Timestamp(year=year, month=month, day=day)

    return _overlay_actual_vs_average(df, bucket_key=bucket_key, bucket_timestamp=half_month_timestamp)


def build_two_hour_overlay(
    df: pd.DataFrame,
    start: datetime,
    end: datetime,
    region: Optional[str] = None,
    equipment: Optional[List[str]] = None,
) -> pd.DataFrame:
    """조회 기간이 "24시간"일 때만 쓰는 장문형(tidy) 데이터: 실제 탐지 추이와 2시간 단위 평균을
    한 그래프에 겹쳐 그릴 수 있도록 (촬영시각, 장비명, 탐지수, 구분) 행으로 만든다.
    구분 값은 "실제"(원본 시점별) / "평균"(2시간 구간의 평균, 구간 시작 시각 대표값)이고, 값이 전부 0인 장비는 뺀다."""
    if region:
        df = df[df["region_name"] == region]
    if equipment is not None:
        df = df[df["class_name"].isin(equipment)]
    df = df[(df["captured_time"] >= start) & (df["captured_time"] < end)]

    bucket = timedelta(hours=2)
    bucket_index = (df["captured_time"] - start) // bucket

    return _overlay_actual_vs_average(
        df,
        bucket_key=bucket_index,
        bucket_timestamp=lambda i: start + i * bucket,
    )


def list_regions() -> List[str]:
    """위치 선택 팝오버에 쓸 지역(region_name) 목록을 돌려준다."""
    return fetch_regions()


def list_equipment_classes(threat_levels: Optional[List[int]] = None) -> List[str]:
    """장비 선택 버튼에 쓸 장비 구분(class_name) 목록을 돌려준다.
    threat_levels가 빈 리스트면(체크박스 전부 해제) 아무 장비도 없이 돌려준다."""
    if threat_levels is not None and not threat_levels:
        return []
    return fetch_equipment_classes(threat_levels)