"""
[EO 탐지 화면]
사용자가 EO(일반 컬러 위성/항공 사진)를 올려 표적을 탐지하고 결과를 보는 페이지.
구조는 sar/view.py와 같다: 입력 컨트롤 → 서비스 호출 → 결과(이미지+표) 표시.
SAR과 달리 컬러 사진이므로 원본 색 그대로 표시한 위에 박스를 그린다.

DB 연동(satellite_intel)은 SAR과 반대 방향이다:
  - 파일명 자체가 메타데이터다. "자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS.png" 형식
    (예: 425-1_개풍군_1_EO_2023-12-30 220000.png, 파일명에 ':'를 못 쓰므로 시각은 붙여 쓴다)
  - 저장 버튼 하나로 image_analysis(처음이면 새 행, 같은 영상 재저장이면 기존 행 재사용·덮어쓰기)와
    detection_result(클래스별 집계, avg_confidence는 미사용 방침이라 0)를 한 번에 저장하고,
    원본·결과 이미지는 S3에만 올린다 (shared/s3_store.py — 로컬 폴더는 조회 시 캐시 전용).
"""
import io
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
from shared.alert_ui import render_change_analysis_result
from shared.change_analysis import analyze_image_change
from shared.database import get_engine
from shared import s3_store
from shared.image_store import image_paths_for, parse_image_meta, save_analysis_and_detections
from shared.viz import draw_boxes

_SESSION_RESULT_KEY = "eo_last_result"
_SESSION_UPLOAD_NAME_KEY = "eo_last_upload_name"
_SESSION_FILE_BYTES_KEY = "eo_last_file_bytes"     # 원본 저장용으로 업로드 바이트를 보관
_SESSION_SAVED_KEY = "eo_last_saved"               # {파일명: image_id} 중복 저장 안내용
_SESSION_FLASH_KEY = "eo_flash_message"            # 수정/삭제/추가 후 rerun에서 보여줄 안내

# 새 박스 추가 시 고를 수 있는 라벨 목록 (EO 모델 클래스 = equipment 테이블의 class_name과 일치).
_EO_LABELS = [
    "SMV",
    "LMV",
    "AFV",
    "MCV",
    "SU-35",
    "B-1B",
    "TU-22",
    "F-15",
    "KC-135",
    "F-22",
    "FA-18",
    "TU-95",
    "KC-10",
    "SU-34",
    "C-130",
    "SU-24",
    "C-17",
    "C-5",
    "F-16",
    "TU-160",
    "B-52",
    "P-3C",
    "Airplane",
    "Helicopter",
]

_DB = "satellite_intel"

# 이미지 파일이 저장될 폴더 (프로젝트 루트 기준).


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
# 2) DB 연동 (satellite_intel) — 파일명 해석/저장은 shared/image_store.py 공용
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


def _save_image_files(
    result: service.EoInferenceResult,
    file_bytes: Optional[bytes],
    original_rel: str,
    result_rel: str,
) -> None:
    """원본과 결과 이미지를 S3에만 올린다 (로컬 폴더는 조회 시 캐시로만 쓰인다).

    업로드 실패 시 예외가 올라가고, 호출부에서 DB 저장 전에 부르므로
    실패하면 DB에는 아무것도 기록되지 않는다.
    """
    if file_bytes:
        s3_store.upload_bytes(original_rel, file_bytes)

    annotated = draw_boxes(result.scene, result.detections)
    buffer = io.BytesIO()
    annotated.save(buffer, format="PNG")
    s3_store.upload_bytes(result_rel, buffer.getvalue())


def render_db_save_section(result: service.EoInferenceResult, meta: Optional[Dict[str, Any]]) -> None:
    """image_analysis·detection_result에 저장될 내용을 미리 보여주고, 버튼 하나로 함께 저장한다."""
    with st.container(border=True):
        st.subheader("DB 저장 (image_analysis + detection_result)")

        if meta is None:
            st.info(
                f"파일명 '{result.filename}'이 저장 형식이 아니어서 DB 저장은 할 수 없습니다. "
                "형식: 자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS "
                "(예: 425-1_개풍군_1_EO_2023-12-30 220000.png — 시각 앞은 공백/밑줄 모두 허용)"
            )
            return

        equipment_ctx = _load_equipment_ids()
        if equipment_ctx["error"]:
            st.warning(f"DB 연결 실패: {equipment_ctx['error']}")
            return

        original_rel, result_rel = image_paths_for(result.filename)

        # 1) image_analysis에 저장될 내용 미리보기 (image_id는 DB가 자동 부여하므로 표시하지 않음).
        with st.expander("image_analysis에 저장될 내용", expanded=False):
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

        with st.expander("detection_result에 저장될 내용", expanded=False):
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

        # 같은 파일을 이미 저장했다면 안내한다 (다시 저장하면 같은 행을 덮어쓴다).
        saved_map = st.session_state.get(_SESSION_SAVED_KEY, {})
        if result.filename in saved_map:
            st.caption(
                f"이미 저장된 파일입니다 (image_id={saved_map[result.filename]}). "
                "다시 저장하면 같은 image_id의 탐지 결과를 덮어씁니다."
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
                image_id = save_analysis_and_detections(
                    meta, original_rel, result_rel, rows, created_at
                )
                outcome = analyze_image_change(image_id)
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
                render_change_analysis_result(outcome)


# =====================================================================
# 4) 결과 표시 — 검출 목록은 sar/view.py와 동일하게 선택/수정/삭제/추가를 지원한다
# =====================================================================

def render_detection_table(rows: List[Dict]) -> List[int]:
    """탐지된 표적 목록을 보여주고, 선택된 행의 라벨/박스 편집 UI를 제공한다."""
    # 기본은 접힌 상태 — 저장 버튼까지의 스크롤을 줄이고, 편집할 때만 펼쳐 쓴다.
    with st.expander(f"검출 목록 ({len(rows)}개)", expanded=False):
        selected_indices: List[int] = []

        if rows:
            dataframe = pd.DataFrame(
                [
                    {
                        "label": item["label"],
                        "x1": item["bbox"][0],
                        "y1": item["bbox"][1],
                        "x2": item["bbox"][2],
                        "y2": item["bbox"][3],
                    }
                    for item in rows
                ]
            )
            event = st.dataframe(
                dataframe,
                use_container_width=True,
                hide_index=True,
                height=210,
                key="eo_detection_table",
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "label": st.column_config.TextColumn("label"),
                    "x1": st.column_config.NumberColumn("x1", format="%.1f"),
                    "y1": st.column_config.NumberColumn("y1", format="%.1f"),
                    "x2": st.column_config.NumberColumn("x2", format="%.1f"),
                    "y2": st.column_config.NumberColumn("y2", format="%.1f"),
                },
            )

            selection = getattr(event, "selection", {})
            if isinstance(selection, dict):
                selected_rows = list(selection.get("rows", []))
            else:
                selected_rows = list(getattr(selection, "rows", []))
            if selected_rows:
                selected_idx = selected_rows[0]
                if 0 <= selected_idx < len(rows):
                    selected = rows[selected_idx]
                    st.caption(f"선택됨: {selected['label']} #{selected_idx + 1}")
                    _render_detection_editor(rows, selected_idx)
                    selected_indices = [selected_idx]
            else:
                st.caption("행을 클릭하면 해당 박스만 표시되고, 라벨과 bbox를 수정/삭제할 수 있습니다.")
        else:
            st.info("탐지된 표적이 없습니다. 필요한 경우 새 박스를 직접 추가할 수 있습니다.")

        _render_add_detection_form(rows)
        return selected_indices


def _render_detection_editor(rows: List[Dict], selected_idx: int) -> None:
    """선택한 detection의 label/bbox를 수정하는 작은 폼을 그린다."""
    selected = rows[selected_idx]
    x1, y1, x2, y2 = [float(value) for value in selected["bbox"]]

    with st.form(key=f"eo_detection_editor_{selected_idx}"):
        edited_label = st.text_input(
            "label",
            value=str(selected["label"]),
            key=f"eo_detection_label_{selected_idx}",
        )
        coord_cols = st.columns(4)
        with coord_cols[0]:
            edited_x1 = st.number_input(
                "x1",
                value=x1,
                step=1.0,
                format="%.1f",
                key=f"eo_detection_x1_{selected_idx}",
            )
        with coord_cols[1]:
            edited_y1 = st.number_input(
                "y1",
                value=y1,
                step=1.0,
                format="%.1f",
                key=f"eo_detection_y1_{selected_idx}",
            )
        with coord_cols[2]:
            edited_x2 = st.number_input(
                "x2",
                value=x2,
                step=1.0,
                format="%.1f",
                key=f"eo_detection_x2_{selected_idx}",
            )
        with coord_cols[3]:
            edited_y2 = st.number_input(
                "y2",
                value=y2,
                step=1.0,
                format="%.1f",
                key=f"eo_detection_y2_{selected_idx}",
            )

        action_cols = st.columns(2)
        with action_cols[0]:
            submitted = st.form_submit_button("수정 적용", use_container_width=True)
        with action_cols[1]:
            delete_clicked = st.form_submit_button("선택 행 삭제", use_container_width=True)

    if delete_clicked:
        deleted_label = str(rows[selected_idx]["label"])
        del rows[selected_idx]
        _update_saved_detections(rows)
        st.session_state[_SESSION_FLASH_KEY] = f"'{deleted_label}' 행을 삭제했습니다."
        st.rerun()

    if not submitted:
        return

    normalized_box = _normalize_bbox([edited_x1, edited_y1, edited_x2, edited_y2])
    rows[selected_idx]["label"] = edited_label.strip() or str(selected["label"])
    rows[selected_idx]["bbox"] = normalized_box
    _update_saved_detections(rows)
    st.session_state[_SESSION_FLASH_KEY] = "수정 내용을 탐지 결과 이미지에 반영했습니다."
    st.rerun()


def _render_add_detection_form(rows: List[Dict]) -> None:
    """사용자가 새 detection 행을 추가하는 폼을 그린다 (미탐 객체를 직접 박스 치는 용도).

    검출 목록이 expander로 바뀌면서 (expander 중첩 불가) 이 폼은 popover로 연다.
    """
    with st.popover("새 박스 추가", use_container_width=True):
        with st.form("eo_add_detection_form"):
            new_label = st.selectbox("label", options=_EO_LABELS)
            coord_cols = st.columns(4)
            with coord_cols[0]:
                new_x1 = st.number_input("x1", value=0.0, step=1.0, format="%.1f")
            with coord_cols[1]:
                new_y1 = st.number_input("y1", value=0.0, step=1.0, format="%.1f")
            with coord_cols[2]:
                new_x2 = st.number_input("x2", value=64.0, step=1.0, format="%.1f")
            with coord_cols[3]:
                new_y2 = st.number_input("y2", value=64.0, step=1.0, format="%.1f")

            submitted = st.form_submit_button("행 추가", use_container_width=True)

    if not submitted:
        return

    rows.append(
        {
            "label": new_label,
            "bbox": _normalize_bbox([new_x1, new_y1, new_x2, new_y2]),
            "conf": None,
        }
    )
    _update_saved_detections(rows)
    st.session_state[_SESSION_FLASH_KEY] = "새 박스를 추가했습니다."
    st.rerun()


def _normalize_bbox(box: List[float]) -> List[float]:
    """좌표 순서가 뒤집혀 입력돼도 [x1, y1, x2, y2] 순서로 맞춘다."""
    x1, y1, x2, y2 = [float(value) for value in box]
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def _update_saved_detections(rows: List[Dict]) -> None:
    """session_state에 저장된 마지막 결과의 detections를 갱신한다."""
    saved_result = st.session_state.get(_SESSION_RESULT_KEY)
    if saved_result is not None:
        saved_result.detections = rows
        st.session_state[_SESSION_RESULT_KEY] = saved_result


def _detections_for_selection(detections: List[Dict], selected_indices: List[int]) -> List[Dict]:
    """선택된 행이 있으면 해당 detection만, 없으면 전체 detection을 돌려준다."""
    selected = [
        detections[index]
        for index in selected_indices
        if 0 <= index < len(detections)
    ]
    return selected or detections


def render_eo_result(result: service.EoInferenceResult) -> None:
    """추론 결과를 요약 줄 → (왼쪽) 박스 그린 이미지 · (오른쪽) 편집 가능한 검출 목록으로 그린다."""
    st.success(f"완료 {result.elapsed_sec}s | 탐지 {len(result.detections)}개")

    flash_message = st.session_state.pop(_SESSION_FLASH_KEY, None)
    if flash_message:
        st.success(flash_message)

    # 왼쪽: 탐지 이미지, 오른쪽: 검출 목록.
    # 표에서 선택한 행을 이미지에 반영해야 하므로 표(오른쪽)를 먼저 그린다.
    image_col, table_col = st.columns([2, 1])
    with table_col:
        selected_indices = render_detection_table(result.detections)
    with image_col:
        st.subheader("탐지 결과")
        selected_detections = _detections_for_selection(result.detections, selected_indices)
        st.image(draw_boxes(result.scene, selected_detections), use_container_width=True)
        if selected_indices:
            st.caption("선택한 행의 박스만 표시 중입니다. 표 선택을 해제하면 전체 박스가 표시됩니다.")


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
    meta = parse_image_meta(result.filename)
    render_db_save_section(result, meta)
