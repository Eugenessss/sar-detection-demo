"""
[지휘관 도메인 - DB 연동]
아군 타격자산(satellite_intel.strike_asset)과 적군 위치(satellite_intel.region)를
조회하는 함수 모음.
  - fetch_strike_assets  : 아군 타격자산 전체 조회 (좌표·사거리 포함)
  - fetch_enemy_location : image_analysis.region_id로 연결된 region의 적군 좌표 조회
연결은 shared/database.py를 쓰고, 값은 전부 파라미터 바인딩으로 넘긴다.
"""
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


def _parse_categories(value: Any) -> List[str]:
    """suitable_target_categories(JSON 컬럼) 값을 파이썬 리스트로 변환한다."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


def fetch_strike_assets() -> List[Dict[str, Any]]:
    """strike_asset 테이블의 아군 타격자산 전체를 조회한다 (좌표·사거리 포함)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT asset_id, asset_name, name, category, range_km, "
                f"response_time_min, suitable_target_categories, notes, "
                f"location_name, latitude, longitude "
                f"FROM `{_DB}`.`strike_asset` ORDER BY asset_id"
            )
        ).fetchall()

    assets: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row._mapping)
        item["suitable_target_categories"] = _parse_categories(item["suitable_target_categories"])
        assets.append(item)
    return assets


def fetch_enemy_location(image_id: int) -> Optional[Dict[str, Any]]:
    """image_id가 속한 지역(region)의 적군 좌표를 조회한다.

    image_analysis.region_id로 region 테이블과 연결된다 (없으면 None).
    """
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT r.region_id, r.latitude, r.longitude "
                f"FROM `{_DB}`.`image_analysis` ia "
                f"JOIN `{_DB}`.`region` r ON ia.region_id = r.region_id "
                f"WHERE ia.image_id = :image_id"
            ),
            {"image_id": image_id},
        ).fetchone()
    return dict(row._mapping) if row else None
