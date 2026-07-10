"""
[지휘관 도메인 - 서비스]
SAR/EO 페이지가 세션(st.session_state)에 남겨둔 마지막 분석 결과를 읽어와
표적을 정리하고, DB(satellite_intel)의 아군 타격자산(strike_asset)·적군 위치(region)를
가져와 직선거리를 계산한 뒤, 사거리(range_km)를 만족하는 자산만 추천/선택 가능하게 하고,
지휘관이 편집할 육하원칙(5W1H) 초안을 만드는 순수 로직.
화면(view.py)이 이 함수들을 직접 호출한다.

주의: feature끼리 서로 import하지 않는다는 프로젝트 원칙을 지키기 위해,
      features.sar / features.eo 모듈을 직접 import하지 않는다. 대신 그 페이지들이
      이미 st.session_state에 저장해 둔 결과 객체를 '읽기 전용'으로만 꺼내 쓴다.
"""
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from features.commander import repository
from features.commander.assets import get_target_category

# SAR 페이지(features/sar/view.py)가 실행 후 저장해두는 세션 키.
_SAR_SESSION_KEY = "sar_last_result"
# EO 페이지는 현재(2026-07) 세션에 결과를 남기지 않는다. 추후 EO 쪽에서 같은 방식으로
# 세션 저장을 추가할 경우를 대비해 키만 미리 정의해둔다.
_EO_SESSION_KEY = "eo_last_result"

_EARTH_RADIUS_KM = 6371.0088   # 하버사인 공식에 쓰는 지구 평균 반지름


@dataclass
class TargetSummary:
    """표적 라벨 하나를 집계한 결과."""
    label: str          # 탐지 라벨 (예: T72, Car ...)
    category: str        # 표적 대분류 (예: 기갑표적)
    count: int            # 탐지 개수
    max_conf: float       # 해당 라벨 중 최고 신뢰도


@dataclass
class LatestAnalysis:
    """세션에서 읽어온 '마지막 분석 결과' 한 벌."""
    source: str                              # "SAR" 또는 "EO"
    filename: str                            # 분석에 쓰인 업로드 파일명
    detections: List[Dict[str, Any]] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)   # 회전각 등 부가정보


@dataclass
class EvaluatedAsset:
    """DB의 아군 타격자산 한 개 + (계산 가능하면) 적군까지의 거리·사거리 충족 여부."""
    asset_id: int
    asset_name: str                 # 운용부대명 (예: 제1포병여단)
    name: str                       # 장비명 (예: K9A1)
    category: str
    range_km: float
    response_time_min: int
    suitable_target_categories: List[str]
    notes: str
    location_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    distance_km: Optional[float] = None   # 적군 위치까지 직선거리 (계산 불가 시 None)
    in_range: Optional[bool] = None       # 사거리 충족 여부 (판정 불가 시 None)


def _first_not_none(item: Dict[str, Any], keys: List[str]) -> Optional[float]:
    """dict에서 keys 순서대로 보며 None이 아닌 첫 값을 돌려준다."""
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def get_latest_analysis() -> Optional[LatestAnalysis]:
    """SAR/EO 페이지가 세션에 남긴 마지막 분석 결과를 찾아온다. 없으면 None.

    SAR 페이지는 실행할 때마다 st.session_state["sar_last_result"]를 갱신하므로,
    이 함수는 그 값을 그대로 읽기만 한다(다른 feature 코드를 건드리지 않음).
    """
    sar_result = st.session_state.get(_SAR_SESSION_KEY)
    if sar_result is not None:
        return LatestAnalysis(
            source="SAR",
            filename=getattr(sar_result, "filename", "알수없음"),
            detections=list(getattr(sar_result, "detections", [])),
            extra={
                "rotate_deg": getattr(sar_result, "rotate_deg", None),
                "azimuth": getattr(sar_result, "azimuth", None),
                "elapsed_sec": getattr(sar_result, "elapsed_sec", None),
            },
        )

    eo_result = st.session_state.get(_EO_SESSION_KEY)
    if eo_result is not None:
        return LatestAnalysis(
            source="EO",
            filename=getattr(eo_result, "filename", "알수없음"),
            detections=list(getattr(eo_result, "detections", [])),
            extra={"elapsed_sec": getattr(eo_result, "elapsed_sec", None)},
        )

    return None


def parse_image_id(filename: Optional[str]) -> Optional[int]:
    """업로드 파일명(예: 8192.tif)에서 image_id를 뽑는다. 숫자 형식이 아니면 None."""
    if not filename:
        return None
    stem = Path(filename).stem
    return int(stem) if stem.isdigit() else None


def summarize_targets(detections: List[Dict[str, Any]]) -> List[TargetSummary]:
    """탐지 목록을 라벨별로 집계해 표적 요약 목록(개수 많은 순)을 돌려준다."""
    labels = [str(item.get("label", "미상")) for item in detections]
    counts = Counter(labels)

    max_conf: Dict[str, float] = {}
    for item in detections:
        label = str(item.get("label", "미상"))
        conf = _first_not_none(item, ["cls_conf", "conf", "det_conf"])
        if conf is None:
            continue
        max_conf[label] = max(max_conf.get(label, 0.0), float(conf))

    summaries = [
        TargetSummary(
            label=label,
            category=get_target_category(label),
            count=count,
            max_conf=round(max_conf.get(label, 0.0), 3),
        )
        for label, count in counts.items()
    ]
    return sorted(summaries, key=lambda s: s.count, reverse=True)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표(위도/경도, 십진도) 사이의 직선거리를 하버사인 공식으로 계산한다 (km)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return round(2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a)), 2)


def _evaluate_assets(
    raw_assets: List[Dict[str, Any]],
    enemy_location: Optional[Dict[str, Any]],
) -> List[EvaluatedAsset]:
    """DB에서 읽은 아군 자산 원본 목록에, 가능하면 적군까지의 거리·사거리 충족 여부를 채운다."""
    enemy_lat = enemy_location.get("latitude") if enemy_location else None
    enemy_lon = enemy_location.get("longitude") if enemy_location else None

    evaluated: List[EvaluatedAsset] = []
    for row in raw_assets:
        distance_km: Optional[float] = None
        in_range: Optional[bool] = None

        if (
            enemy_lat is not None
            and enemy_lon is not None
            and row.get("latitude") is not None
            and row.get("longitude") is not None
        ):
            distance_km = haversine_km(
                float(enemy_lat), float(enemy_lon),
                float(row["latitude"]), float(row["longitude"]),
            )
            in_range = distance_km <= float(row["range_km"])

        evaluated.append(
            EvaluatedAsset(
                asset_id=int(row["asset_id"]),
                asset_name=row["asset_name"],
                name=row["name"],
                category=row["category"],
                range_km=float(row["range_km"]),
                response_time_min=int(row["response_time_min"]),
                suitable_target_categories=row.get("suitable_target_categories") or [],
                notes=row.get("notes") or "",
                location_name=row.get("location_name"),
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
                distance_km=distance_km,
                in_range=in_range,
            )
        )
    return evaluated


def get_assets_and_enemy(filename: Optional[str]) -> Dict[str, Any]:
    """DB에서 아군 자산 목록과 적군 위치를 함께 가져와 거리/사거리 충족 여부까지 계산한다.

    DB 조회가 실패해도 화면이 죽지 않도록 error 메시지로 감싸서 돌려준다.
    돌려주는 dict: {"image_id", "enemy_location", "assets"(EvaluatedAsset 목록), "error"}
    """
    image_id = parse_image_id(filename)

    enemy_location = None
    try:
        if image_id is not None:
            enemy_location = repository.fetch_enemy_location(image_id)
    except Exception as exc:
        return {"image_id": image_id, "enemy_location": None, "assets": [], "error": str(exc)}

    try:
        raw_assets = repository.fetch_strike_assets()
    except Exception as exc:
        return {"image_id": image_id, "enemy_location": enemy_location, "assets": [], "error": str(exc)}

    evaluated = _evaluate_assets(raw_assets, enemy_location)
    return {"image_id": image_id, "enemy_location": enemy_location, "assets": evaluated, "error": None}


def recommend_assets(
    target_summaries: List[TargetSummary],
    evaluated_assets: List[EvaluatedAsset],
) -> List[Dict[str, Any]]:
    """표적 요약을 바탕으로 자산별 적합도 점수를 매긴다.

    점수 = 그 자산이 대응 가능한 표적 대분류에 속하는 표적들의 (개수 x 신뢰도) 합.
    사거리 밖(in_range=False)인 자산은 점수와 무관하게 목록 뒤쪽으로 보낸다
    (화면에서 참고용으로 보여주되 선택은 못 하게 하기 위함).
    """
    scored: List[Dict[str, Any]] = []
    for asset in evaluated_assets:
        score = 0.0
        matched_labels: List[str] = []
        for summary in target_summaries:
            if summary.category in asset.suitable_target_categories:
                score += summary.count * max(summary.max_conf, 0.1)
                matched_labels.append(summary.label)
        scored.append(
            {
                "asset": asset,
                "score": round(score, 2),
                "matched_labels": matched_labels,
            }
        )

    # 정렬 기준: ① 사거리 밖(in_range is False)인 자산을 뒤로, ② 그 안에서는 점수 높은 순
    scored.sort(key=lambda entry: (entry["asset"].in_range is False, -entry["score"]))
    return scored


def build_5w1h_draft(
    analysis: LatestAnalysis,
    target_summaries: List[TargetSummary],
    selected_asset: EvaluatedAsset,
) -> Dict[str, str]:
    """선택된 자산과 분석 결과를 바탕으로 육하원칙(5W1H) 초안을 만든다.

    화면에서 지휘관이 각 항목을 자유롭게 수정할 수 있도록 '초안'만 제공한다.
    """
    target_text = ", ".join(
        f"{s.label}({s.category}) {s.count}개" for s in target_summaries
    ) or "탐지된 표적 없음"

    distance_text = (
        f", 표적까지 거리 약 {selected_asset.distance_km}km"
        if selected_asset.distance_km is not None
        else ""
    )

    return {
        "누가": f"{selected_asset.asset_name} ({selected_asset.name})",
        "언제": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "어디서": (
            f"{analysis.source} 분석 이미지 '{analysis.filename}' 좌표 기준 "
            "(정확한 지역명·좌표는 지휘관 확인 후 수정 필요)"
        ),
        "무엇을": target_text,
        "어떻게": (
            f"{selected_asset.category} 운용 "
            f"(사거리 {selected_asset.range_km}km, 대응시간 약 {selected_asset.response_time_min}분"
            f"{distance_text})"
        ),
        "왜": f"{analysis.source} 영상판독 결과 상기 표적이 식별되어 무력화가 필요하다고 판단됨",
    }


def format_order_text(decision: Dict[str, str]) -> str:
    """육하원칙 dict를 사람이 읽는 명령문 텍스트 한 벌로 조립한다."""
    lines = ["[지휘관 결심 및 명령]", ""]
    for key in ["누가", "언제", "어디서", "무엇을", "어떻게", "왜"]:
        lines.append(f"- {key}: {decision.get(key, '')}")
    return "\n".join(lines)
