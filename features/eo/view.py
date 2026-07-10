"""
[EO 탐지 화면]
사용자가 EO(일반 컬러 위성/항공 사진)를 올려 표적을 탐지하고 결과를 보는 페이지.
구조는 sar/view.py와 같다: 입력 컨트롤 → 서비스 호출 → 결과(이미지+표) 표시.
SAR과 달리 컬러 사진이므로 원본 색 그대로 표시한 위에 박스를 그린다.

DB 연동(satellite_intel)은 SAR과 반대 방향이다:
  - 파일명 자체가 메타데이터다. "자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS.png" 형식
    (예: 425-1_개풍군_1_EO_2023-12-30 220000.png, 파일명에 ':'를 못 쓰므로 시각은 붙여 쓴다)
  - 저장 버튼 하나로 image_analysis(새 행, image_id는 DB가 자동 증가로 부여)와
    detection_result(클래스별 집계, avg_confidence는 미사용 방침이라 0)를 한 번에 저장하고,
    원본 이미지는 original_image/, 박스가 그려진 결과 이미지는 result_image/ 폴더에 저장한다.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy import text

from features.eo import service
from features.eo.loader import load_eo_models
from shared.database import get_engine
from shared.viz import draw_boxes

_SESSION_RESULT_KEY = "eo_last_result"
_SESSION_UPLOAD_NAME_KEY = "eo_last_upload_name"
_SESSION_FILE_BYTES_KEY = "eo_last_file_bytes"     # 원본 저장용으로 업로드 바이트를 보관
_SESSION_SAVED_KEY = "eo_last_saved"               # {파일명: image_id} 중복 저장 안내용

_DB = "satellite_intel"

# 이미지 파일이 저장될 폴더 (프로젝트 루트 기준).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ORIGINAL_DIR = _PROJECT_ROOT / "original_image"
_RESULT_DIR = _PROJECT_ROOT / "result_image"


# =====================================================================
# 1) 입력 컨트롤
# =====================================================================

@dataclass
class EoControls:
    """입력 영역에서 사용자가 고른 값들을 한 꾸러미로 담아 전달한다."""
    image_file: Optional[Any]
    run_clicked: bool


def render_eo_controls() -> EoControls:
    """파일 업로드·실행 버튼을 그리고, 사용자가 고른 값을 돌려준다."""
    st.subheader("입력")
    upload_col, action_col = st.columns(
        [2.0, 1.0],
        vertical_alignment="bottom",
    )

    with upload_col:
        image_file = st.file_uploader(
            "이미지 업로드 (JPG / PNG / TIF)",
            type=["jpg", "jpeg", "png", "tif", "tiff"],
        )

    with action_col:
        # EO 모델을 (프로세스당 1번) 로드하고 그 상태를 표시한다.
        loaded, error = load_eo_models()
        if loaded:
            st.success("모델 로드됨")
        else:
            st.error(f"모델 미로드: {error or ''}")
        run_clicked = st.button("실행", type="primary", use_container_width=True)

    st.divider()

    return EoControls(image_file=image_file, run_clicked=run_clicked)


# =====================================================================
# 2) 파일명 → image_analysis 메타데이터 해석
# =====================================================================

def _parse_image_meta(filename: Optional[str]) -> Optional[Dict[str, Any]]:
    """파일명에서 image_analysis에 저장할 메타데이터를 뽑는다.

    형식: "자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS.확장자"
    (예: 425-1_개풍군_1_EO_2023-12-30 220000.png)
    형식이 다르면 None을 돌려준다 (DB 저장 없이 탐지 기능만 사용 가능).
    """
    if not filename:
        return None
    parts = Path(filename).stem.split("_")
    if len(parts) != 5:
        return None

    asset_name, region_name, region_id_raw, sensor_raw, time_raw = parts
    if not region_id_raw.isdigit():
        return None
    sensor_type = sensor_raw.upper()
    if sensor_type not in ("EO", "SAR"):
        return None
    try:
        # 파일명에는 ':'를 쓸 수 없어 시각을 붙여 쓴다 (220000 → 22:00:00).
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


def _image_paths_for(filename: str) -> Tuple[str, str]:
    """원본/결과 이미지가 저장될 경로(DB에 기록할 프로젝트 기준 상대경로)를 만든다."""
    original_rel = f"original_image/{filename}"
    result_rel = f"result_image/{Path(filename).stem}.png"
    return original_rel, result_rel


# =====================================================================
# 3) DB 연동 (satellite_intel)
# =====================================================================

@st.cache_data(ttl=60, show_spinner=False)
def _load_equipment_ids() -> Dict[str, Any]:
    """equipment 사전 {class_name: equipment_id}를 조회한다 (실패해도 화면이 죽지 않게 error로 전달)."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(f"SELECT class_name, equipment_id FROM `{_DB}`.`equipment`")
            ).fetchall()
        return {"equipment": {row[0]: int(row[1]) for row in rows}, "error": None}
    except Exception as exc:
        return {"equipment": {}, "error": str(exc)}


def _save_analysis_and_detections(
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


def _save_image_files(
    result: service.EoInferenceResult,
    file_bytes: Optional[bytes],
    original_rel: str,
    result_rel: str,
) -> None:
    """원본 이미지는 original_image/, 박스가 그려진 결과 이미지는 result_image/에 저장한다."""
    _ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
    _RESULT_DIR.mkdir(parents=True, exist_ok=True)

    if file_bytes:
        (_PROJECT_ROOT / original_rel).write_bytes(file_bytes)

    annotated = draw_boxes(result.scene, result.detections)
    annotated.save(_PROJECT_ROOT / result_rel)


def render_db_save_section(result: service.EoInferenceResult, meta: Optional[Dict[str, Any]]) -> None:
    """image_analysis·detection_result에 저장될 내용을 미리 보여주고, 버튼 하나로 함께 저장한다."""
    with st.container(border=True):
        st.subheader("DB 저장 (image_analysis + detection_result)")

        if meta is None:
            st.info(
                "파일명이 저장 형식이 아니어서 DB 저장은 할 수 없습니다. "
                "형식: 자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS "
                "(예: 425-1_개풍군_1_EO_2023-12-30 220000.png)"
            )
            return

        equipment_ctx = _load_equipment_ids()
        if equipment_ctx["error"]:
            st.warning(f"DB 연결 실패: {equipment_ctx['error']}")
            return

        original_rel, result_rel = _image_paths_for(result.filename)

        # 1) image_analysis에 저장될 내용 미리보기 (image_id는 DB가 자동 부여하므로 표시하지 않음).
        st.caption("image_analysis에 저장될 내용")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "자산": meta["asset_name"],
                        "지역": meta["region_name"],
                        "region_id": meta["region_id"],
                        "센서": meta["sensor_type"],
                        "촬영시각": meta["captured_time"],
                        "original_image_path": original_rel,
                        "result_image_path": result_rel,
                    }
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

        # 2) detection_result에 저장될 집계 미리보기 (클래스별 개수, avg_confidence=0).
        counts = Counter(str(det["label"]) for det in result.detections)
        equipment = equipment_ctx["equipment"]
        matched = {label: cnt for label, cnt in counts.items() if label in equipment}
        skipped = sorted(set(counts) - set(matched))

        st.caption("detection_result에 저장될 내용")
        if matched:
            st.dataframe(
                pd.DataFrame(
                    [
                        {"클래스": label, "equipment_id": equipment[label], "수량": cnt}
                        for label, cnt in sorted(matched.items())
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("저장할 탐지 결과가 없습니다 (image_analysis만 저장됩니다).")
        if skipped:
            st.warning(f"equipment에 없는 라벨은 저장에서 제외됩니다: {', '.join(skipped)}")

        # 같은 파일을 이미 저장했다면 안내한다 (버튼을 다시 누르면 새 image_id로 추가 저장됨).
        saved_map = st.session_state.get(_SESSION_SAVED_KEY, {})
        if result.filename in saved_map:
            st.caption(
                f"이미 저장된 파일입니다 (image_id={saved_map[result.filename]}). "
                "다시 저장하면 새 image_id로 한 행 더 추가됩니다."
            )

        # 3) 저장 버튼 하나로 이미지 파일 2개 + 두 테이블을 함께 저장한다.
        if st.button("DB 저장", type="primary", use_container_width=True, key="eo_db_save"):
            created_at = datetime.now()   # 버튼을 누른 시스템 시간을 created_at으로 기록
            rows = [(equipment[label], cnt) for label, cnt in sorted(matched.items())]
            try:
                _save_image_files(
                    result,
                    st.session_state.get(_SESSION_FILE_BYTES_KEY),
                    original_rel,
                    result_rel,
                )
                image_id = _save_analysis_and_detections(
                    meta, original_rel, result_rel, rows, created_at
                )
            except Exception as exc:
                st.error(f"DB 저장 실패: {exc}")
            else:
                saved_map[result.filename] = image_id
                st.session_state[_SESSION_SAVED_KEY] = saved_map
                st.success(
                    f"저장 완료: image_id={image_id} (자동 부여), "
                    f"detection_result {len(rows)}개 클래스, "
                    f"원본 → {original_rel}, 결과 → {result_rel} "
                    f"({created_at:%Y-%m-%d %H:%M:%S})"
                )


# =====================================================================
# 4) 결과 표시
# =====================================================================

def render_detection_table(rows: List[Dict]) -> None:
    """탐지된 표적 목록을 표(클래스·신뢰도)로 보여준다. 없으면 안내 문구."""
    if not rows:
        st.info("탐지된 표적이 없습니다.")
        return

    st.subheader(f"검출 목록 ({len(rows)}개)")
    dataframe = pd.DataFrame(
        [
            {
                "label": item["label"],
                "conf": round(item["conf"], 3),
            }
            for item in rows
        ]
    )
    st.dataframe(dataframe, use_container_width=True, hide_index=True)


def render_eo_result(result: service.EoInferenceResult) -> None:
    """추론 결과를 요약 줄 → (왼쪽) 박스 그린 이미지 · (오른쪽) 검출 표로 그린다."""
    st.success(f"완료 {result.elapsed_sec}s | 탐지 {len(result.detections)}개")

    # 왼쪽: 탐지 이미지, 오른쪽: 검출 결과 표
    image_col, table_col = st.columns([2, 1])
    with image_col:
        st.subheader("탐지 결과")
        st.image(draw_boxes(result.scene, result.detections), use_container_width=True)
    with table_col:
        render_detection_table(result.detections)


# =====================================================================
# 5) 세션 상태 — DB 저장 버튼 클릭(rerun) 후에도 결과를 유지한다
# =====================================================================

def _save_result(
    result: service.EoInferenceResult,
    upload_name: Optional[str],
    file_bytes: bytes,
) -> None:
    """DB 저장 버튼 클릭 등 rerun 이후에도 쓸 수 있게 마지막 추론 결과·원본 바이트를 저장한다."""
    st.session_state[_SESSION_RESULT_KEY] = result
    st.session_state[_SESSION_UPLOAD_NAME_KEY] = upload_name
    st.session_state[_SESSION_FILE_BYTES_KEY] = file_bytes


def _clear_saved_result() -> None:
    """파일이 바뀌거나 실패했을 때 이전 추론 결과를 지운다."""
    for key in [_SESSION_RESULT_KEY, _SESSION_UPLOAD_NAME_KEY, _SESSION_FILE_BYTES_KEY]:
        st.session_state.pop(key, None)


def _sync_saved_result_with_upload(controls: EoControls) -> None:
    """업로드 파일이 바뀌었는데 새 실행 전이라면 이전 결과를 숨긴다."""
    upload_name = controls.image_file.name if controls.image_file is not None else None
    saved_upload_name = st.session_state.get(_SESSION_UPLOAD_NAME_KEY)
    if not controls.run_clicked and upload_name != saved_upload_name:
        _clear_saved_result()


# =====================================================================
# 6) 페이지 진입점
# =====================================================================

def render_eo_page() -> None:
    """EO 탐지 페이지 전체를 그린다: 입력 받기 → 실행 시 추론 → 결과 표시."""
    st.title("EO 표적 탐지")
    st.caption("YOLO 기반 EO(전자광학) 위성·항공 영상 표적 후보 탐지")

    controls = render_eo_controls()
    _sync_saved_result_with_upload(controls)

    if controls.run_clicked:
        if controls.image_file is None:
            st.warning("이미지를 업로드하세요.")
            st.stop()

        file_bytes = controls.image_file.getvalue()
        with st.spinner("추론 중입니다. CPU 환경에서는 시간이 걸릴 수 있습니다."):
            try:
                result = service.run_inference(file_bytes, controls.image_file.name)
            except service.ModelUnavailableError as exc:
                _clear_saved_result()
                st.error(str(exc))
                st.stop()
            except Exception as exc:
                _clear_saved_result()
                st.error(f"추론 실패: {exc}")
                st.stop()

        _save_result(result, controls.image_file.name, file_bytes)

    result: Optional[service.EoInferenceResult] = st.session_state.get(_SESSION_RESULT_KEY)
    if result is None:
        return

    render_eo_result(result)

    # 탐지 이미지 아래: 파일명에서 읽은 메타데이터로 두 테이블 + 이미지 파일을 한 번에 저장.
    meta = _parse_image_meta(result.filename)
    render_db_save_section(result, meta)
