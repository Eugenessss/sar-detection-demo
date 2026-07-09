"""
[SAR 도메인 - DB 연동]
SAR 페이지가 satellite_intel 스키마와 주고받는 조회/저장 함수 모음.
  - fetch_image_info       : 투입 이미지 정보 조회 (image_analysis)
  - fetch_equipment_ids    : 클래스 이름 → equipment_id 사전 (equipment)
  - save_detection_results : 탐지 집계 저장 (detection_result, 같은 image_id는 덮어씀)
연결은 shared/database.py를 쓰고, 값은 전부 파라미터 바인딩으로 넘긴다.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


def fetch_image_info(image_id: int) -> Optional[Dict[str, Any]]:
    """image_analysis에서 투입 이미지 정보 4컬럼을 조회한다 (없으면 None)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT asset_name, region_name, sensor_type, captured_time "
                f"FROM `{_DB}`.`image_analysis` WHERE image_id = :image_id"
            ),
            {"image_id": image_id},
        ).fetchone()
    return dict(row._mapping) if row else None


def fetch_equipment_ids() -> Dict[str, int]:
    """equipment 사전을 {class_name: equipment_id} 형태로 돌려준다 (라벨→ID 변환용)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT class_name, equipment_id FROM `{_DB}`.`equipment`")
        ).fetchall()
    return {row[0]: int(row[1]) for row in rows}


def save_detection_results(
    image_id: int,
    class_counts: List[Tuple[int, int]],
    created_at: datetime,
) -> int:
    """탐지 집계 [(equipment_id, 개수), ...]를 detection_result에 저장한다.

    같은 image_id의 기존 행은 지우고 새로 넣는다 (재실행 시 중복 누적 방지).
    avg_confidence는 미사용 방침이라 0으로 채운다 (컬럼이 NOT NULL이라 빈값 불가).
    created_at은 화면에서 저장 버튼을 누른 시각을 받아 그대로 기록한다.
    """
    with get_engine().begin() as conn:   # begin(): 성공 시 커밋, 예외 시 전체 롤백
        conn.execute(
            text(f"DELETE FROM `{_DB}`.`detection_result` WHERE image_id = :image_id"),
            {"image_id": image_id},
        )
        for equipment_id, count in class_counts:
            conn.execute(
                text(
                    f"INSERT INTO `{_DB}`.`detection_result` "
                    f"(image_id, equipment_id, detected_count, avg_confidence, created_at) "
                    f"VALUES (:image_id, :equipment_id, :count, 0, :created_at)"
                ),
                {
                    "image_id": image_id,
                    "equipment_id": equipment_id,
                    "count": count,
                    "created_at": created_at,
                },
            )
    return len(class_counts)
