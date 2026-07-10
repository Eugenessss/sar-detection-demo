"""
[Statistics 도메인 - 서비스]
시작일·기간 필터로 조회 범위를 계산하고, 탐지 통계를 화면이 바로 그릴 수 있는
표(DataFrame)·그래프용 피벗으로 가공하는 순수 파이썬 함수.
흐름: resolve_range(범위 계산) → repository.fetch_detection_stats(조회) → pivot_time_series(그래프 가공).
지역(region_name) 목록은 list_regions로 따로 조회해 화면의 위치 선택 팝오버에 쓴다.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from features.statistics.repository import fetch_detection_stats, fetch_equipment_classes, fetch_regions

# 화면에 노출할 기간 선택지와 실제 timedelta 매핑 (선택 버튼 라벨 = 이 딕셔너리 키).
INTERVALS: Dict[str, timedelta] = {
    "12시간": timedelta(hours=12),
    "24시간": timedelta(hours=24),
    "1주": timedelta(weeks=1),
    "1개월": timedelta(days=30),
    "1년": timedelta(days=365),
}

DEFAULT_INTERVAL = "1주"


@dataclass
class StatisticsResult:
    """통계 화면이 그대로 그릴 수 있는 형태로 담은 결과."""
    start: datetime
    end: datetime
    raw: pd.DataFrame   # 원본 조회 결과 (지역 필터링·표 표시에 함께 쓰인다)


def resolve_range(start_date: date, interval_label: str) -> Tuple[datetime, datetime]:
    """시작 날짜와 기간 라벨로 (시작시각, 종료시각)을 계산한다."""
    start = datetime.combine(start_date, datetime.min.time())
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


def pivot_time_series(
    df: pd.DataFrame,
    region: Optional[str] = None,
    equipment: Optional[List[str]] = None,
) -> pd.DataFrame:
    """촬영시각 x 장비명 피벗(선 그래프용)을 만든다. region이 주어지면 그 지역만, equipment가 주어지면 그 장비들만 남긴다."""
    if region:
        df = df[df["region_name"] == region]
    if equipment is not None:
        df = df[df["class_name"].isin(equipment)]
    return df.pivot_table(
        index="captured_time", columns="class_name", values="detected_count", aggfunc="sum"
    ).fillna(0)


def list_regions() -> List[str]:
    """위치 선택 팝오버에 쓸 지역(region_name) 목록을 돌려준다."""
    return fetch_regions()


def list_equipment_classes() -> List[str]:
    """장비 선택 버튼에 쓸 장비 구분(class_name) 목록을 돌려준다."""
    return fetch_equipment_classes()