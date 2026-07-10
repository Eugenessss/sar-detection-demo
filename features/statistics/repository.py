"""
[Statistics 도메인 - DB 연동]
detection_result를 image_analysis·equipment와 엮어 기간별 탐지 통계를 조회하는 함수 모음.
연결은 shared/database.py를 쓰고, 값(기간)은 전부 파라미터 바인딩으로 넘긴다.
"""
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


def fetch_detection_stats(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """[start, end] 기간에 촬영된 이미지의 탐지 집계를 장비명·지역과 함께 조회한다."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT e.class_name, dr.detected_count, ia.captured_time, ia.region_name "
                f"FROM `{_DB}`.`detection_result` dr "
                f"INNER JOIN `{_DB}`.`image_analysis` ia ON dr.image_id = ia.image_id "
                f"INNER JOIN `{_DB}`.`equipment` e ON dr.equipment_id = e.equipment_id "
                f"WHERE ia.captured_time BETWEEN :start_dt AND :end_dt "
                f"ORDER BY ia.captured_time ASC"
            ),
            {"start_dt": start, "end_dt": end},
        ).fetchall()
    return [dict(row._mapping) for row in rows]


def fetch_regions() -> List[str]:
    """image_analysis에 있는 지역(region_name) 목록을 중복 없이 돌려준다 (위치 필터용)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT region_name FROM `{_DB}`.`image_analysis` ORDER BY region_name")
        ).fetchall()
    return [row[0] for row in rows]


def fetch_equipment_classes() -> List[str]:
    """equipment에 있는 장비 구분(class_name) 목록을 중복 없이 돌려준다 (장비 필터용)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT class_name FROM `{_DB}`.`equipment` ORDER BY class_name")
        ).fetchall()
    return [row[0] for row in rows]