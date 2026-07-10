"""
[공용 - 영상 등록]
파일명 메타데이터 해석과 image_analysis/detection_result 저장을 담당한다.
SAR/EO 탐지 화면이 똑같이 쓰던 로직이라 shared로 올렸다 (두 화면의 복사본을 대체).
  - parse_image_meta            : "자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS" 파일명 해석
  - image_paths_for             : 원본/결과 이미지의 저장 상대경로 생성
  - save_analysis_and_detections: 두 테이블 저장. 같은 (자산·지역·시각·센서) 영상은
                                  기존 행을 재사용하고 탐지 결과를 덮어쓴다 (중복 행 방지)
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DB = "satellite_intel"


def parse_image_meta(filename: Optional[str]) -> Optional[Dict[str, Any]]:
    """파일명에서 image_analysis에 저장할 메타데이터를 뽑는다.

    형식: "자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS.확장자"
    (예: 425-1_개풍군_1_SAR_2026-07-09 100000.tif)
    시각 앞 공백 대신 밑줄(..._2026-07-09_100000)로 써도 허용한다 — 가장 흔한 실수라서.
    형식이 다르면 None을 돌려준다 (DB 저장 없이 탐지 기능만 사용 가능).
    """
    if not filename:
        return None
    parts = Path(filename).stem.split("_")
    # "YYYY-MM-DD_HHMMSS"처럼 밑줄로 쓴 경우 날짜와 시각을 도로 합쳐준다.
    if len(parts) == 6 and re.fullmatch(r"\d{6}", parts[5]):
        parts = parts[:4] + [f"{parts[4]} {parts[5]}"]
    if len(parts) != 5:
        return None

    asset_name, region_name, region_id_raw, sensor_raw, time_raw = parts
    if not region_id_raw.isdigit():
        return None
    sensor_type = sensor_raw.upper()
    if sensor_type not in ("EO", "SAR"):
        return None
    try:
        # 파일명에는 ':'를 쓸 수 없어 시각을 붙여 쓴다 (100000 → 10:00:00).
        captured_time = datetime.strptime(time_raw, "%Y-%m-%d %H%M%S")
    except ValueError:
        return None

    return {
        "asset_name": asset_name,
        "region_name": region_name,
        "region_id": int(region_id_raw),
        "sensor_type": sensor_type,
        "captured_time": captured_time,
    }


def image_paths_for(filename: str) -> Tuple[str, str]:
    """원본/결과 이미지가 저장될 경로(DB에 기록할 프로젝트 기준 상대경로)를 만든다."""
    original_rel = f"original_image/{filename}"
    result_rel = f"result_image/{Path(filename).stem}.png"
    return original_rel, result_rel


def save_analysis_and_detections(
    meta: Dict[str, Any],
    original_rel: str,
    result_rel: str,
    class_counts: List[Tuple[int, int]],
    created_at: datetime,
) -> int:
    """image_analysis 행을 확보하고, 그 image_id로 detection_result 집계를 함께 저장한다.

    같은 (자산, 지역, 촬영시각, 센서) 영상이 이미 있으면 새 행을 만들지 않고 그 image_id를
    재사용하며, detection_result는 지우고 다시 넣는다 (재저장 = 덮어쓰기 — 중복 행이 생기면
    이후 영상의 '직전 영상' 판정이 왜곡되기 때문).
    처음 보는 영상이면 image_id는 DB가 auto_increment로 부여한다.
    두 테이블 저장은 하나의 트랜잭션이라, 중간에 실패하면 둘 다 되돌아간다.
    avg_confidence는 미사용 방침이라 0으로 채운다 (컬럼이 NOT NULL이라 빈값 불가).
    돌려주는 값은 (재사용했거나 새로 부여된) image_id.
    """
    from sqlalchemy import text

    from shared.database import get_engine

    with get_engine().begin() as conn:   # begin(): 성공 시 커밋, 예외 시 전체 롤백
        existing = conn.execute(
            text(
                f"SELECT image_id FROM `{_DB}`.`image_analysis` "
                "WHERE asset_name = :asset_name AND region_name = :region_name "
                "AND captured_time = :captured_time AND sensor_type = :sensor_type "
                "ORDER BY image_id DESC LIMIT 1"
            ),
            {
                "asset_name": meta["asset_name"],
                "region_name": meta["region_name"],
                "captured_time": meta["captured_time"],
                "sensor_type": meta["sensor_type"],
            },
        ).fetchone()

        if existing:
            # 재저장: 같은 영상 행을 재사용하고, 경로와 탐지 결과를 현재 내용으로 덮어쓴다.
            image_id = int(existing[0])
            conn.execute(
                text(
                    f"UPDATE `{_DB}`.`image_analysis` "
                    "SET region_id = :region_id, "
                    "    original_image_path = :original_path, "
                    "    result_image_path = :result_path "
                    "WHERE image_id = :image_id"
                ),
                {
                    "region_id": meta["region_id"],
                    "original_path": original_rel,
                    "result_path": result_rel,
                    "image_id": image_id,
                },
            )
            conn.execute(
                text(f"DELETE FROM `{_DB}`.`detection_result` WHERE image_id = :image_id"),
                {"image_id": image_id},
            )
        else:
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
