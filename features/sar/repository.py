"""
[SAR 도메인 - DB 연동]
SAR 페이지가 satellite_intel 스키마와 주고받는 조회/저장 함수 모음.
EO 페이지와 같은 방식이다: 파일명이 메타데이터를 담고, 저장 버튼 한 번에
image_analysis(새 행, image_id는 DB가 자동 부여)와 detection_result(클래스별 집계)를
하나의 트랜잭션으로 저장한다.
  - fetch_equipment_ids          : 클래스 이름 → equipment_id 사전 (equipment)
  - save_analysis_and_detections : 두 테이블 동시 저장, 새 image_id 반환
연결은 shared/database.py를 쓰고, 값은 전부 파라미터 바인딩으로 넘긴다.
"""
from datetime import datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


def fetch_equipment_ids() -> Dict[str, int]:
    """equipment 사전을 {class_name: equipment_id} 형태로 돌려준다 (라벨→ID 변환용)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT class_name, equipment_id FROM `{_DB}`.`equipment`")
        ).fetchall()
    return {row[0]: int(row[1]) for row in rows}


def save_analysis_and_detections(
    meta: Dict[str, Any],
    original_rel: str,
    result_rel: str,
    class_counts: List[Tuple[int, int]],
    created_at: datetime,
) -> int:
    """image_analysis에 새 행을 넣고, 그 image_id로 detection_result 집계를 함께 저장한다.

    image_id는 지정하지 않는다 — DB가 auto_increment로 1씩 증가시켜 부여한다.
    두 테이블 저장은 하나의 트랜잭션이라, 중간에 실패하면 둘 다 되돌아간다.
    avg_confidence는 미사용 방침이라 0으로 채운다 (컬럼이 NOT NULL이라 빈값 불가).
    created_at은 화면에서 저장 버튼을 누른 시각을 받아 그대로 기록한다.
    돌려주는 값은 새로 부여된 image_id.
    """
    with get_engine().begin() as conn:   # begin(): 성공 시 커밋, 예외 시 전체 롤백
        result = conn.execute(
            text(
                f"INSERT INTO `{_DB}`.`image_analysis` "
                f"(asset_name, region_name, region_id, sensor_type, captured_time, "
                f" original_image_path, result_image_path) "
                f"VALUES (:asset_name, :region_name, :region_id, :sensor_type, :captured_time, "
                f"        :original_path, :result_path)"
            ),
            {
                "asset_name": meta["asset_name"],
                "region_name": meta["region_name"],
                "region_id": meta["region_id"],
                "sensor_type": meta["sensor_type"],
                "captured_time": meta["captured_time"],
                "original_path": original_rel,
                "result_path": result_rel,
            },
        )
        image_id = int(result.lastrowid)

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
    return image_id
