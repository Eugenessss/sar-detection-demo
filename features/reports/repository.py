"""
[Reports 도메인 - DB 연동]
image_analysis 목록(내림차순)과 선택한 영상의 상세·탐지 집계를 조회하는 함수 모음.
연결은 shared/database.py를 쓰고, 값은 전부 파라미터 바인딩으로 넘긴다 (읽기 전용).
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


def fetch_image_list(sensor: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """image_analysis를 image_id 내림차순으로 조회한다 (sensor가 EO/SAR면 그 센서만)."""
    safe_limit = max(1, min(int(limit), 1000))
    where = "WHERE sensor_type = :sensor " if sensor in ("EO", "SAR") else ""
    params: Dict[str, Any] = {"limit": safe_limit}
    if where:
        params["sensor"] = sensor

    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT image_id, asset_name, region_name, sensor_type, captured_time, "
                f"       result_image_path, created_at "
                f"FROM `{_DB}`.`image_analysis` "
                f"{where}"
                f"ORDER BY image_id DESC LIMIT :limit"
            ),
            params,
        ).fetchall()
    return [dict(row._mapping) for row in rows]


def fetch_image_detail(image_id: int) -> Optional[Dict[str, Any]]:
    """선택한 영상 한 건의 전체 정보를 조회한다 (없으면 None)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT image_id, asset_name, region_name, region_id, sensor_type, "
                f"       captured_time, original_image_path, result_image_path, created_at "
                f"FROM `{_DB}`.`image_analysis` WHERE image_id = :image_id"
            ),
            {"image_id": image_id},
        ).fetchone()
    return dict(row._mapping) if row else None


def fetch_detections(image_id: int) -> List[Dict[str, Any]]:
    """선택한 영상의 탐지 집계를 장비 이름·분류·위협등급과 함께 조회한다."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT e.class_name, e.category, e.threat_level, "
                f"       dr.detected_count, dr.created_at "
                f"FROM `{_DB}`.`detection_result` dr "
                f"INNER JOIN `{_DB}`.`equipment` e ON dr.equipment_id = e.equipment_id "
                f"WHERE dr.image_id = :image_id "
                f"ORDER BY e.threat_level ASC, dr.detected_count DESC"
            ),
            {"image_id": image_id},
        ).fetchall()
    return [dict(row._mapping) for row in rows]
