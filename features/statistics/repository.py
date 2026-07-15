"""
[Statistics 도메인 - DB 연동]
detection_result를 image_analysis·equipment와 엮어 기간별 탐지 통계를 조회하는 함수 모음.
연결은 shared/database.py를 쓰고, 값(기간)은 전부 파라미터 바인딩으로 넘긴다.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

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


def fetch_latest_captured_time() -> Optional[datetime]:
    """image_analysis에서 가장 최근 촬영시각을 돌려준다 (행이 없으면 None)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT MAX(captured_time) FROM `{_DB}`.`image_analysis`")
        ).fetchone()
    return row[0] if row and row[0] is not None else None


def fetch_latest_captured_time_by_region() -> Dict[str, datetime]:
    """지역별 가장 최근 촬영시각을 {region_name: captured_time}으로 돌려준다.

    분석 현황의 지역별 24시간 추이가 지역마다 자기 마지막 촬영 시점을 끝점으로
    창을 잡을 때 쓴다 (지역별 촬영 주기가 어긋나도 각 지역이 항상 그려지도록)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT region_name, MAX(captured_time) "
                f"FROM `{_DB}`.`image_analysis` "
                f"WHERE region_name IS NOT NULL "
                f"GROUP BY region_name"
            )
        ).fetchall()
    return {row[0]: row[1] for row in rows if row[1] is not None}


def fetch_regions() -> List[str]:
    """image_analysis에 있는 지역(region_name) 목록을 중복 없이 돌려준다 (위치 필터용)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT region_name FROM `{_DB}`.`image_analysis` ORDER BY region_name")
        ).fetchall()
    return [row[0] for row in rows]


def fetch_equipment_classes(threat_levels: Optional[List[int]] = None) -> List[str]:
    """equipment에 있는 장비 구분(class_name) 목록을 중복 없이 돌려준다 (장비 필터용).
    threat_levels가 주어지면 그 위협등급(1/2/3)에 속한 장비만 돌려준다."""
    where = ""
    params: Dict[str, Any] = {}
    if threat_levels:
        placeholders = ", ".join(f":tl{i}" for i in range(len(threat_levels)))
        where = f"WHERE threat_level IN ({placeholders}) "
        params = {f"tl{i}": level for i, level in enumerate(threat_levels)}

    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT class_name FROM `{_DB}`.`equipment` {where}ORDER BY class_name"),
            params,
        ).fetchall()
    return [row[0] for row in rows]