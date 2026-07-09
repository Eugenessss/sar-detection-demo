"""
[SAR 추론 화면]
사용자가 실제로 보는 SAR 추론 페이지.
좌측에는 입력·요약·검출 목록을 두고, 우측에는 박스가 그려진 탐지 결과 이미지를 보여준다.

읽는 순서(위→아래):
  1) 입력 컨트롤   : 회전 설정·파일 업로드·모델 상태·실행 버튼
  2) 결과 표시     : 요약 배너·검출 목록·탐지 이미지
  3) 페이지 진입점 : 좌우 레이아웃을 만들고 실행 흐름을 연결
"""
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from features.sar import repository, service
from features.sar.loader import load_sar_models
from shared.viz import draw_boxes

_SESSION_RESULT_KEY = "sar_last_result"
_SESSION_UPLOAD_NAME_KEY = "sar_last_upload_name"
_SESSION_FLASH_KEY = "sar_flash_message"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_ROOT = _PROJECT_ROOT / "outputs" / "sar"


# =====================================================================
# 1) 입력 컨트롤
# =====================================================================

@dataclass
class InferenceControls:
    """입력 영역에서 사용자가 고른 값들을 한 꾸러미로 담아 전달한다."""
    tif_file: Optional[Any]
    rotate_k: int
    run_clicked: bool


def _inject_layout_css() -> None:
    """Streamlit 기본 UI로 부족한 빈 결과 영역만 최소 CSS로 보정한다."""
    st.markdown(
        """
        <style>
        .sar-placeholder {
            min-height: 360px;
            border: 1px dashed rgba(140, 140, 140, 0.65);
            border-radius: 8px;
            background: rgba(128, 128, 128, 0.08);
            color: rgba(160, 160, 160, 0.95);
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            font-size: 0.95rem;
        }
        .sar-result-note {
            color: rgba(150, 150, 150, 0.95);
            font-size: 0.8rem;
            margin-top: 0.45rem;
            text-align: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_inference_controls() -> InferenceControls:
    """회전·파일 업로드·실행 버튼을 그리고, 사용자가 고른 값을 돌려준다."""
    with st.container(border=True):
        st.subheader("입력")

        with st.expander("수동 회전", expanded=True):
            manual_rot = st.select_slider(
                "회전 각도",
                options=[0, 90, 180, 270],
                value=0,
                format_func=lambda value: f"{value}도",
            )
            rotate_k = manual_rot // 90

        tif_file = st.file_uploader(
            "이미지 업로드 (TIF / PNG / JPG)",
            type=["tif", "tiff", "png", "jpg", "jpeg"],
        )

        # SAR 모델을 (프로세스당 1번) 로드하고 그 상태를 표시한다.
        loaded, error = load_sar_models()
        if loaded:
            st.success("모델 로드됨")
        else:
            st.error(f"모델 미로드: {error or ''}")

        run_clicked = st.button("실행", type="primary", use_container_width=True)

    return InferenceControls(
        tif_file=tif_file,
        rotate_k=rotate_k,
        run_clicked=run_clicked,
    )


# =====================================================================
# 2) 결과 표시
# =====================================================================

def render_run_summary(result: service.SarInferenceResult) -> None:
    """실행 완료 후 소요 시간·탐지 수·회전 정보를 한 줄로 보여준다."""
    parts = [
        f"완료 {result.elapsed_sec}s",
        f"탐지 {len(result.detections)}개",
        f"회전 {result.rotate_deg}도 ({'자동' if result.auto_rotation else '수동'})",
    ]
    if result.azimuth is not None:
        parts.append(f"방위각 {result.azimuth}도")
    st.success(" | ".join(parts))


# =====================================================================
# 2-1) DB 연동 (satellite_intel)
# =====================================================================

def _parse_image_id(filename: Optional[str]) -> Optional[int]:
    """파일명(예: 8192.tif)에서 image_id를 뽑는다. 숫자 형식이 아니면 None."""
    if not filename:
        return None
    stem = Path(filename).stem
    return int(stem) if stem.isdigit() else None


@st.cache_data(ttl=60, show_spinner=False)
def _load_db_context(image_id: int) -> Dict[str, Any]:
    """이미지 정보와 equipment 사전을 한 번에 조회한다 (실패해도 화면이 죽지 않게 error로 전달)."""
    try:
        return {
            "info": repository.fetch_image_info(image_id),
            "equipment": repository.fetch_equipment_ids(),
            "error": None,
        }
    except Exception as exc:
        return {"info": None, "equipment": {}, "error": str(exc)}


def render_image_info_card(image_id: Optional[int], db_ctx: Dict[str, Any]) -> None:
    """투입 이미지의 DB 정보(자산·지역·센서·촬영시각)를 보여준다."""
    with st.container(border=True):
        st.subheader("투입 이미지 정보")
        if image_id is None:
            st.info("파일명이 image_id 형식이 아니어서 DB와 연동되지 않습니다. (예: 8192.tif)")
            return
        if db_ctx["error"]:
            st.warning(f"DB 연결 실패: {db_ctx['error']}")
            return
        info = db_ctx["info"]
        if info is None:
            st.info(f"image_analysis에 image_id={image_id} 이미지가 없습니다.")
            return
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "image_id": image_id,
                        "자산": info["asset_name"],
                        "지역": info["region_name"],
                        "센서": info["sensor_type"],
                        "촬영시각": info["captured_time"],
                    }
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_db_save_section(
    result: service.SarInferenceResult,
    image_id: Optional[int],
    db_ctx: Dict[str, Any],
) -> None:
    """detection_result에 저장될 집계를 미리 보여주고, 버튼을 누르면 저장한다."""
    with st.container(border=True):
        st.subheader("DB 저장 (detection_result)")

        if image_id is None or db_ctx["error"] or db_ctx["info"] is None:
            st.caption("DB(image_analysis)에 등록된 이미지만 저장할 수 있습니다.")
            return

        # 최종 검출목록(편집 반영된 상태)을 클래스별 개수로 집계한다.
        counts = Counter(str(det["label"]) for det in result.detections)
        equipment = db_ctx["equipment"]
        matched = {label: cnt for label, cnt in counts.items() if label in equipment}
        skipped = sorted(set(counts) - set(matched))

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
            st.info("저장할 탐지 결과가 없습니다.")
        if skipped:
            st.warning(f"equipment에 없는 라벨은 저장에서 제외됩니다: {', '.join(skipped)}")

        if st.button("DB 저장", use_container_width=True, disabled=not matched, key="sar_db_save"):
            created_at = datetime.now()   # 버튼을 누른 시스템 시간을 created_at으로 기록
            rows = [(equipment[label], cnt) for label, cnt in sorted(matched.items())]
            try:
                saved = repository.save_detection_results(image_id, rows, created_at)
            except Exception as exc:
                st.error(f"DB 저장 실패: {exc}")
            else:
                st.success(
                    f"저장 완료: image_id={image_id}, {saved}개 클래스 "
                    f"({created_at:%Y-%m-%d %H:%M:%S})"
                )


def render_detection_table(rows: List[Dict]) -> List[int]:
    """탐지된 차량 목록을 보여주고, 선택된 행의 라벨/박스 편집 UI를 제공한다."""
    with st.container(border=True):
        st.subheader(f"검출 목록 ({len(rows)}개)")
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
                key="sar_detection_table",
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
            st.info("탐지된 차량이 없습니다. 필요한 경우 새 박스를 직접 추가할 수 있습니다.")

        _render_add_detection_form(rows)
        return selected_indices


def _render_detection_editor(rows: List[Dict], selected_idx: int) -> None:
    """선택한 detection의 label/bbox를 수정하는 작은 폼을 그린다."""
    selected = rows[selected_idx]
    x1, y1, x2, y2 = [float(value) for value in selected["bbox"]]

    with st.form(key=f"sar_detection_editor_{selected_idx}"):
        edited_label = st.text_input(
            "label",
            value=str(selected["label"]),
            key=f"sar_detection_label_{selected_idx}",
        )
        coord_cols = st.columns(4)
        with coord_cols[0]:
            edited_x1 = st.number_input(
                "x1",
                value=x1,
                step=1.0,
                format="%.1f",
                key=f"sar_detection_x1_{selected_idx}",
            )
        with coord_cols[1]:
            edited_y1 = st.number_input(
                "y1",
                value=y1,
                step=1.0,
                format="%.1f",
                key=f"sar_detection_y1_{selected_idx}",
            )
        with coord_cols[2]:
            edited_x2 = st.number_input(
                "x2",
                value=x2,
                step=1.0,
                format="%.1f",
                key=f"sar_detection_x2_{selected_idx}",
            )
        with coord_cols[3]:
            edited_y2 = st.number_input(
                "y2",
                value=y2,
                step=1.0,
                format="%.1f",
                key=f"sar_detection_y2_{selected_idx}",
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
    """사용자가 새 detection 행을 추가하는 폼을 그린다."""
    with st.expander("새 박스 추가", expanded=not rows):
        with st.form("sar_add_detection_form"):
            new_label = st.text_input("label", value="New")
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
            "label": new_label.strip() or "New",
            "bbox": _normalize_bbox([new_x1, new_y1, new_x2, new_y2]),
            "det_conf": None,
            "cls_conf": None,
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


def render_result_panel(
    result: Optional[service.SarInferenceResult],
    selected_indices: Optional[List[int]] = None,
) -> None:
    """우측 결과 카드에 placeholder 또는 박스 오버레이 이미지를 표시한다."""
    with st.container(border=True):
        st.subheader("탐지 결과")

        if result is None:
            st.markdown(
                """
                <div class="sar-placeholder">
                    이미지를 업로드하고 실행하면<br>탐지 결과가 표시됩니다.
                </div>
                <div class="sar-result-note">SAR 이미지 + 박스 오버레이</div>
                """,
                unsafe_allow_html=True,
            )
            return

        selected_detections = _detections_for_selection(result.detections, selected_indices or [])
        st.image(draw_boxes(result.scene, selected_detections), use_container_width=True)
        if selected_indices:
            st.caption("선택한 행의 박스만 표시 중입니다. 표 선택을 해제하면 전체 박스가 표시됩니다.")
        else:
            st.caption("SAR 이미지 + 박스 오버레이")

        if st.button("최종 결과 이미지 저장", use_container_width=True):
            try:
                saved_path = _save_annotated_result_image(result)
            except Exception as exc:
                st.error(f"이미지 저장 실패: {exc}")
            else:
                st.success(f"저장 완료: {saved_path}")
                if selected_indices:
                    st.info("저장된 이미지는 선택 행이 아니라 최종 검출목록 전체 기준입니다.")


def run_inference_if_requested(
    controls: InferenceControls,
) -> Tuple[Optional[service.SarInferenceResult], Optional[str]]:
    """실행 버튼이 눌렸으면 추론 서비스를 호출하고 (결과, 오류 메시지)를 돌려준다."""
    if not controls.run_clicked:
        return None, None

    if controls.tif_file is None:
        return None, "이미지를 업로드하세요."

    try:
        result = service.run_inference(
            controls.tif_file.getvalue(),
            controls.tif_file.name,
            controls.rotate_k,
        )
    except service.ModelUnavailableError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"추론 실패: {exc}"

    return result, None


def _detections_for_selection(detections: List[Dict], selected_indices: List[int]) -> List[Dict]:
    """선택된 행이 있으면 해당 detection만, 없으면 전체 detection을 돌려준다."""
    selected = [
        detections[index]
        for index in selected_indices
        if 0 <= index < len(detections)
    ]
    return selected or detections


def _save_annotated_result_image(result: service.SarInferenceResult) -> Path:
    """최종 수정된 detections 전체를 반영한 결과 이미지를 outputs 폴더에 저장한다."""
    now = datetime.now()
    output_dir = _OUTPUT_ROOT / now.strftime("%Y-%m-%d") / _output_run_name(result, now)
    output_dir.mkdir(parents=True, exist_ok=True)

    image = draw_boxes(result.scene, result.detections)
    image_path = output_dir / "annotated.png"
    image.save(image_path)
    return image_path


def _output_run_name(result: service.SarInferenceResult, saved_at: datetime) -> str:
    """저장 폴더 이름에 쓸 안전한 실행 이름을 만든다."""
    stem = Path(result.filename or "sar_result").stem
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "sar_result"
    return f"{saved_at:%Y%m%d_%H%M%S_%f}_{safe_stem}"


def _clear_saved_result() -> None:
    """파일이 바뀌거나 실패했을 때 이전 추론 결과를 지운다."""
    for key in [
        _SESSION_RESULT_KEY,
        _SESSION_UPLOAD_NAME_KEY,
        _SESSION_FLASH_KEY,
    ]:
        st.session_state.pop(key, None)


def _save_result(result: service.SarInferenceResult, upload_name: Optional[str]) -> None:
    """행 선택 rerun 이후에도 쓸 수 있게 마지막 추론 결과를 저장한다."""
    st.session_state[_SESSION_RESULT_KEY] = result
    st.session_state[_SESSION_UPLOAD_NAME_KEY] = upload_name


def _sync_saved_result_with_upload(controls: InferenceControls) -> None:
    """업로드 파일이 바뀌었는데 새 실행 전이라면 이전 결과를 숨긴다."""
    upload_name = controls.tif_file.name if controls.tif_file is not None else None
    saved_upload_name = st.session_state.get(_SESSION_UPLOAD_NAME_KEY)
    if not controls.run_clicked and upload_name != saved_upload_name:
        _clear_saved_result()


# =====================================================================
# 3) 페이지 진입점
# =====================================================================

def render_sar_page() -> None:
    """SAR 추론 페이지 전체를 그린다: 입력 받기 → 실행 시 추론 → 결과 표시."""
    _inject_layout_css()

    st.title("DOM SAR 차량 탐지")
    st.caption("YOLO11n + ConvNeXt-Tiny 기반 14종 차량 분류")

    left_col, right_col = st.columns([0.38, 0.62], gap="large")

    with left_col:
        controls = render_inference_controls()
    _sync_saved_result_with_upload(controls)

    result: Optional[service.SarInferenceResult] = st.session_state.get(_SESSION_RESULT_KEY)
    error_message: Optional[str] = None

    if controls.run_clicked and controls.tif_file is not None:
        with right_col:
            with st.spinner("추론 중입니다. CPU 환경에서는 시간이 걸릴 수 있습니다."):
                result, error_message = run_inference_if_requested(controls)
        if error_message:
            _clear_saved_result()
        elif result is not None:
            _save_result(result, controls.tif_file.name)
    else:
        _, error_message = run_inference_if_requested(controls)

    selected_indices: List[int] = []
    with left_col:
        if error_message:
            st.warning(error_message)
        if result is not None:
            render_run_summary(result)
            image_id = _parse_image_id(result.filename)
            db_ctx = (
                _load_db_context(image_id)
                if image_id is not None
                else {"info": None, "equipment": {}, "error": None}
            )
            render_image_info_card(image_id, db_ctx)
            flash_message = st.session_state.pop(_SESSION_FLASH_KEY, None)
            if flash_message:
                st.success(flash_message)
            selected_indices = render_detection_table(result.detections)
            render_db_save_section(result, image_id, db_ctx)

    with right_col:
        render_result_panel(result, selected_indices)
