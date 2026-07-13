"""
[SAR 도메인 - DB 연동]
SAR 페이지가 satellite_intel 스키마와 주고받는 조회 함수 모음.
  - fetch_equipment_ids : 클래스 이름 → equipment_id 사전 (equipment)
저장(image_analysis/detection_result)은 shared/image_store.py의 공용
save_analysis_and_detections를 사용한다 (이 파일의 구버전 복사본은 제거됨 —
중복 방지 로직이 없어 '직전 영상' 판정을 왜곡할 수 있었다).
연결은 shared/database.py를 쓰고, 값은 전부 파라미터 바인딩으로 넘긴다.
"""
from typing import Dict

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
