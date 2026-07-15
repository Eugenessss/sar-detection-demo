"""
[EO/SAR 통합 탐지 화면]
기존 eo/view.py와 sar/view.py를 한 페이지로 합친 화면. 두 페이지는 흐름이 같아서
(업로드 → 탐지 → 편집 가능한 검출 목록 → DB 저장) 하나로 통합했다.

입력은 로컬 업로드가 아니라 S3 원본 풀에서 고른다:
  - S3의 original_image/ 프리픽스가 "분석할 원본 저장소"다. 목록에서 파일을 고르면
    S3에서 받아(로컬 캐시) 추론에 투입한다. 분석 여부(image_analysis 존재)를 뱃지로 보여준다.
  - 파일명 형식: "자산명_지역명_지역ID_센서_YYYY-MM-DD 시각.확장자"
    (예: 425-1_개풍군_1_EO_2023-12-30 220000.png / 425-1_개풍군_1_SAR_2026-08-10 1000000.tif)
  - 센서 자리가 EO면 EO 탐지 가중치로, SAR이면 SAR 탐지+분류 파이프라인으로 실행하고,
    결과 표시도 각 센서의 기존 페이지와 같은 내용(요약·검출 목록·박스 이미지)으로 나온다.

DB 저장 규칙은 SAR/EO 페이지와 동일하다 (공용 shared/image_store 사용):
  - 경로(=S3 키)는 파일명을 그대로 쓴다 (예: original_image/425-1_..., result_image/425-1_....png).
    원본은 이미 S3 원본 풀에 있으므로 다시 올리지 않고, 결과 이미지만 업로드한 뒤 DB에
    기록한다 (업로드 실패 시 DB에 아무것도 남지 않음). 과거 image_id 이름(8199.png 등)으로
    저장된 객체는 DB가 그 경로를 기억하므로 조회에 문제없다.

화면 배치:
  - 상단: 워크플로 진행 바(+일일 체크리스트 팝오버) → 원본 선택 카드.
  - 왼쪽(넓게): 고정 높이 영상 뷰어 — 선택 전 빈 안내, 선택 후 원본 미리보기,
    실행 후 박스가 그려진 탐지 이미지 (이미지 크기와 무관하게 페이지 높이가 일정).
  - 오른쪽(워크플로 레일): 요약 → 검출 목록(편집) → DB 저장 → 보고서.
    판독 업무가 오른쪽 한 열에서 위에서 아래로 끝난다.
"""
import base64
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import streamlit as st
from sqlalchemy import text

from features.eo import service as eo_service
# 보고서 양식·조회는 Reports 페이지 모듈을 그대로 재사용한다 (양식을 한 곳에서만 관리).
from features.reports import report as analysis_report
from features.reports import repository as reports_repository
from features.eo.loader import load_eo_models
from features.sar import service as sar_service
from features.sar.loader import load_sar_models
from shared import s3_store
from shared.alert_ui import render_change_analysis_result
from shared.change_analysis import analyze_image_change
from shared.database import get_engine
from shared.image_store import image_paths_for, save_analysis_and_detections
from shared.ui import (
    InfoItem,
    render_empty_state,
    render_info_strip,
    render_page_header,
    render_section_header,
)
from shared.viz import draw_boxes

# EO/SAR 결과 객체를 함께 다루기 위한 타입 (필드 중 detections/elapsed_sec/filename/scene은 공통).
InferenceResult = Union["eo_service.EoInferenceResult", "sar_service.SarInferenceResult"]

_SESSION_RESULT_KEY = "eosar_last_result"
_SESSION_SENSOR_KEY = "eosar_last_sensor"          # 마지막 실행에 쓴 센서 (EO/SAR)
_SESSION_UPLOAD_NAME_KEY = "eosar_last_upload_name"
_SESSION_FILE_BYTES_KEY = "eosar_last_file_bytes"  # 원본 저장용으로 업로드 바이트를 보관
_SESSION_FLASH_KEY = "eosar_flash_message"         # 수정/삭제/추가 후 rerun에서 보여줄 안내
_SESSION_SAVED_NAME_KEY = "eosar_saved_name"       # 마지막으로 DB 저장까지 마친 파일명 (워크플로 04 표시용)

_DB = "satellite_intel"

# EO에서 새 박스 추가 시 고를 수 있는 라벨 목록 (EO 모델 클래스 = equipment의 class_name과 일치).
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


# =====================================================================
# 0) 파일명 → 메타데이터 해석 (shared/image_store.py보다 시각 자리수에 유연한 통합판)
# =====================================================================

def _parse_captured_time(date_part: str, time_part: str) -> Optional[datetime]:
    """날짜("YYYY-MM-DD")와 시각 숫자를 datetime으로 바꾼다.

    파일명에는 ':'를 쓸 수 없어 시각을 숫자로 붙여 쓰는데, 자리수가 들쭉날쭉해도 받아준다:
      4자리 "1000" → 10:00:00 / 6자리 "100000" → 10:00:00 / 7자리 이상 "1000000" → 앞 6자리만 사용.
    """
    digits = re.sub(r"\D", "", time_part)
    if len(digits) == 4:        # HHMM
        digits += "00"
    elif len(digits) >= 6:      # HHMMSS (넘치는 뒷자리는 무시)
        digits = digits[:6]
    else:
        return None
    try:
        return datetime.strptime(f"{date_part} {digits}", "%Y-%m-%d %H%M%S")
    except ValueError:
        return None


def parse_image_meta(filename: Optional[str]) -> Optional[Dict[str, Any]]:
    """파일명에서 image_analysis에 저장할 메타데이터를 뽑는다.

    형식: "자산명_지역명_지역ID_센서_YYYY-MM-DD 시각.확장자"
    (예: 425-1_개풍군_1_SAR_2026-08-10 1000000.tif — 시각 앞은 공백/밑줄 모두 허용)
    형식이 다르면 None을 돌려준다 (센서를 알 수 없으므로 이 페이지에서는 실행 불가).
    """
    if not filename:
        return None
    parts = Path(filename).stem.split("_")
    # "YYYY-MM-DD_100000"처럼 시각 앞을 밑줄로 쓴 경우 날짜와 시각을 도로 합쳐준다.
    if len(parts) == 6 and re.fullmatch(r"\d{4,}", parts[5]):
        parts = parts[:4] + [f"{parts[4]} {parts[5]}"]
    if len(parts) != 5:
        return None

    asset_name, region_name, region_id_raw, sensor_raw, time_raw = parts
    if not region_id_raw.isdigit():
        return None
    sensor_type = sensor_raw.upper()
    if sensor_type not in ("EO", "SAR"):
        return None

    time_tokens = time_raw.split()
    if len(time_tokens) != 2:
        return None
    captured_time = _parse_captured_time(time_tokens[0], time_tokens[1])
    if captured_time is None:
        return None

    return {
        "asset_name": asset_name,
        "region_name": region_name,
        "region_id": int(region_id_raw),
        "sensor_type": sensor_type,
        "captured_time": captured_time,
    }


# =====================================================================
# 1) 헤더 — 로고 + 제목 (Streamlit 기본 위젯만 사용)
# =====================================================================

def _render_header() -> None:
    """로고와 제목·설명을 페이지 상단에 그린다."""
    render_page_header(
        "EO/SAR 판독",
        "원본 영상의 센서를 자동 식별하고 전용 모델로 표적을 탐지한 뒤 검출 결과와 보고서를 관리합니다.",
        eyebrow="MULTI-SENSOR DETECTION",
        status="판독 시스템 준비",
    )


_WORKFLOW_STEPS = [
    ("01", "SELECT", "원본 선택"),
    ("02", "DETECT", "모델 실행"),
    ("03", "REVIEW", "검출 검토"),
    ("04", "ARCHIVE", "저장·보고"),
]


def _workflow_html(selected: bool, has_result: bool, saved: bool) -> str:
    """세션 상태로 판단한 진행 단계를 반영해 워크플로 바 HTML을 만든다.

    각 단계는 완료(is-done)·진행 중(is-active)·대기(is-todo) 셋 중 하나로 표시된다.
    """
    if saved:
        states = ["done", "done", "done", "done"]
    elif has_result:
        states = ["done", "done", "active", "todo"]
    elif selected:
        states = ["done", "active", "todo", "todo"]
    else:
        states = ["active", "todo", "todo", "todo"]

    steps = [
        f'<div class="ui-workflow-step is-{state}">'
        f"<b>{number}</b><span><small>{eyebrow}</small>{label}</span></div>"
        for (number, eyebrow, label), state in zip(_WORKFLOW_STEPS, states)
    ]
    return (
        '<nav class="ui-workflow" aria-label="EO/SAR 판독 작업 순서">'
        + '<i aria-hidden="true"></i>'.join(steps)
        + "</nav>"
    )


# =====================================================================
# 2) 입력 컨트롤 — 파일명에서 센서를 읽어 그에 맞는 모델 상태를 보여준다
# =====================================================================

@dataclass
class EosarControls:
    """입력 영역에서 사용자가 고른 값들을 한 꾸러미로 담아 전달한다."""
    filename: Optional[str]          # 선택한 원본의 파일명 (S3 키의 basename)
    s3_key: Optional[str]            # 선택한 원본의 S3 키 (original_image/파일명)
    meta: Optional[Dict[str, Any]]   # 파일명에서 해석한 메타데이터 (형식이 다르면 None)
    rotate_k: int                    # SAR 전용 수동 회전 (EO에서는 무시됨)
    run_clicked: bool


@st.cache_data(ttl=60, show_spinner=False)
def _list_s3_originals() -> Dict[str, Any]:
    """S3 original_image/ 목록과 분석 여부를 조회한다 (60초 캐시).

    파일명 형식이 맞는(=메타데이터가 있는) 객체만 목록에 넣는다. 분석 여부는
    image_analysis에 같은 (자산, 지역ID, 센서, 촬영시각) 행이 있는지로 판정한다.
    """
    try:
        keys = s3_store.list_keys("original_image/")
    except Exception as exc:
        return {"items": [], "error": str(exc)}

    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT asset_name, region_id, sensor_type, captured_time "
                    f"FROM `{_DB}`.`image_analysis`"
                )
            ).fetchall()
        analyzed = {(r[0], int(r[1]), r[2], r[3]) for r in rows}
    except Exception:
        analyzed = set()   # DB가 안 되면 뱃지 없이 목록만 보여준다

    items = []
    for key in keys:
        name = key.split("/", 1)[1] if "/" in key else key
        meta = parse_image_meta(name)
        if not name or meta is None:
            continue   # 형식이 다르면 센서를 알 수 없어 이 페이지에서 실행 불가
        done = (
            meta["asset_name"], meta["region_id"], meta["sensor_type"], meta["captured_time"]
        ) in analyzed
        items.append({"name": name, "key": key, "analyzed": done})
    return {"items": items, "error": None}


# 파일명 클릭으로 고른 원본을 rerun 사이에 기억하는 세션 키 ({"name":…, "key":…}).
_SESSION_S3_SELECTED_KEY = "eosar_selected_s3_original"


def render_controls() -> EosarControls:
    """전체 폭 선택 카드 안에 원본 목록과 실행 설정을 좌우로 그린다.

    원본 선택은 스크롤 목록에서 파일명 버튼을 클릭하는 방식이다. 선택하면 아래 영상
    작업영역에 원본 미리보기가 뜨고, 실행을 누르면 탐지 결과 이미지로 바뀐다.
    """
    with st.container(key="panel_eosar_controls"):
        render_section_header(
            "원본 영상 선택",
            "S3 원본 목록에서 판독 대상을 선택하면 센서와 모델을 자동 확인합니다.",
            badge="INPUT",
        )

        listing = _list_s3_originals()
        if listing["error"]:
            st.error(f"S3 목록 조회 실패: {listing['error']}")
        items = listing["items"]

        # 선택 상태는 세션에 기억한다. 목록에서 사라진 파일(삭제/이름변경)이면 선택 해제.
        selected: Optional[Dict[str, Any]] = st.session_state.get(_SESSION_S3_SELECTED_KEY)
        if selected is not None and all(item["key"] != selected["key"] for item in items):
            selected = None
            st.session_state.pop(_SESSION_S3_SELECTED_KEY, None)

        filename = selected["name"] if selected else None
        s3_key = selected["key"] if selected else None
        meta = parse_image_meta(filename) if filename else None
        rotate_k = 0

        source_col, setup_col = st.columns([0.6, 0.4], gap="large", vertical_alignment="top")

        with source_col:
            refresh_col, count_col = st.columns([0.32, 0.68], vertical_alignment="center")
            with refresh_col:
                if st.button("목록 새로고침", use_container_width=True):
                    _list_s3_originals.clear()
                    st.rerun()
            with count_col:
                waiting = sum(1 for item in items if not item["analyzed"])
                st.caption(f"원본 {len(items)}개 (분석 대기 {waiting}개)")

            # 파일명을 그대로 버튼으로 나열한다 — 클릭하면 선택되고, 선택된 것은 강조색.
            if items:
                with st.container(height=210, border=True, key="eosar_source_list"):
                    for item in items:
                        is_selected = selected is not None and item["key"] == selected["key"]
                        label = f"{item['name']}  ·  {'분석됨' if item['analyzed'] else '대기'}"
                        if st.button(
                            label,
                            key=f"eosar_s3_item_{item['key']}",
                            type="primary" if is_selected else "secondary",
                            use_container_width=True,
                        ):
                            st.session_state[_SESSION_S3_SELECTED_KEY] = {
                                "name": item["name"], "key": item["key"],
                            }
                            st.rerun()
            else:
                st.info("S3 original_image/에 분석 가능한 원본이 없습니다.")

        with setup_col:
            if filename is None:
                render_empty_state(
                    "원본을 선택하세요",
                    "왼쪽 목록에서 파일을 선택하면 센서·자산·촬영시각과 모델 상태를 확인할 수 있습니다.",
                    symbol="01",
                )
            else:
                render_info_strip(
                    [
                        InfoItem("센서", meta["sensor_type"], "primary"),
                        InfoItem("자산", meta["asset_name"]),
                        InfoItem("지역", meta["region_name"]),
                        InfoItem("촬영시각", f'{meta["captured_time"]:%Y-%m-%d %H:%M}'),
                    ],
                    compact=True,
                )
                sensor = meta["sensor_type"]
                loader = load_eo_models if sensor == "EO" else load_sar_models
                loaded, error = loader()
                if loaded:
                    st.success(f"{sensor} 모델 로드됨")
                else:
                    st.error(f"{sensor} 모델 미로드: {error or ''}")

                # SAR일 때만 수동 회전 컨트롤을 노출한다 (파일명 방위각 자동 회전이 우선).
                if meta["sensor_type"] == "SAR":
                    with st.expander("수동 회전 (SAR 전용)", expanded=False):
                        manual_rot = st.select_slider(
                            "회전 각도",
                            options=[0, 90, 180, 270],
                            value=0,
                            format_func=lambda value: f"{value}도",
                        )
                        rotate_k = manual_rot // 90

            run_clicked = st.button(
                "분석 실행",
                type="primary",
                use_container_width=True,
                disabled=filename is None,   # 원본을 골라야 실행할 수 있다
            )

    return EosarControls(
        filename=filename,
        s3_key=s3_key,
        meta=meta,
        rotate_k=rotate_k,
        run_clicked=run_clicked,
    )


# 일일 체크리스트: 판독관의 하루 업무 3단계로 고정 (판독 → 경보 → 보고).
# 각 항목은 이 시스템의 실제 기능과 1:1로 대응한다 — 신규 영상 판독(아래 원본 목록의
# '대기' 소화), 미확인 경보 처리(Alerts 페이지), 분석 보고서 작성(아래 보고서 카드).
# 체크 상태는 세션(위젯 상태)에만 저장되어 새로고침 시 초기화된다.
_DAILY_CHECKLIST_ITEMS = ["신규 영상 판독", "미확인 경보 처리", "분석 보고서 작성"]


def _render_workflow_row() -> None:
    """워크플로 진행 표시(왼쪽)와 일일 체크리스트 팝오버(오른쪽)를 한 줄에 그린다."""
    selected = st.session_state.get(_SESSION_S3_SELECTED_KEY) is not None
    has_result = st.session_state.get(_SESSION_RESULT_KEY) is not None
    saved = (
        has_result
        and st.session_state.get(_SESSION_SAVED_NAME_KEY) is not None
        and st.session_state.get(_SESSION_SAVED_NAME_KEY)
        == st.session_state.get(_SESSION_UPLOAD_NAME_KEY)
    )

    with st.container(key="panel_eosar_workflow"):
        bar_col, checklist_col = st.columns([0.78, 0.22], vertical_alignment="center")

        with bar_col:
            st.html(_workflow_html(selected, has_result, saved))

        with checklist_col:
            # 위젯 key 값은 클릭 직후 rerun 시작 시점에 이미 갱신돼 있어,
            # 그리기 전에 읽어도 라벨의 완료 수가 정확하다.
            done_count = sum(
                bool(st.session_state.get(f"eosar_daily_chk_{idx}", False))
                for idx in range(len(_DAILY_CHECKLIST_ITEMS))
            )
            with st.popover(
                f"일일 체크리스트 {done_count}/{len(_DAILY_CHECKLIST_ITEMS)}",
                use_container_width=True,
            ):
                for idx, item in enumerate(_DAILY_CHECKLIST_ITEMS):
                    st.checkbox(item, key=f"eosar_daily_chk_{idx}")


# =====================================================================
# 3) DB 연동 (satellite_intel) — 파일 이름을 image_id로 저장하는 통합판
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


def _find_existing_image_id(meta: Dict[str, Any]) -> Optional[int]:
    """같은 (자산, 지역ID, 촬영시각, 센서) 영상이 이미 등록돼 있으면 그 image_id를 돌려준다."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT image_id FROM `{_DB}`.`image_analysis` "
                "WHERE asset_name = :asset_name AND region_id = :region_id "
                "AND captured_time = :captured_time AND sensor_type = :sensor_type "
                "ORDER BY image_id DESC LIMIT 1"
            ),
            {
                "asset_name": meta["asset_name"],
                "region_id": meta["region_id"],
                "captured_time": meta["captured_time"],
                "sensor_type": meta["sensor_type"],
            },
        ).fetchone()
    return int(row[0]) if row else None


def _save_all(
    meta: Dict[str, Any],
    filename: str,
    annotated_image,
    class_counts: List[Tuple[int, int]],
    created_at: datetime,
) -> Tuple[int, str, str]:
    """결과 이미지를 S3에 올리고, 두 테이블을 공용 저장 로직으로 기록한다.

    경로는 SAR/EO 페이지와 같은 규칙(파일명 유지)을 쓴다 — 원본은 S3 원본 풀
    (original_image/파일명)에서 골라온 것이므로 이미 그 키에 있고, 다시 올리지 않는다.
    결과 업로드 → DB 저장 순서라, 업로드가 실패하면 DB에는 아무것도 남지 않는다.
    행 재사용(같은 자산·지역ID·센서·시각 덮어쓰기)은 image_store가 처리한다.
    돌려주는 값은 (image_id, 원본 상대경로, 결과 상대경로).
    """
    original_rel, result_rel = image_paths_for(filename)

    buffer = io.BytesIO()
    annotated_image.save(buffer, format="PNG")
    s3_store.upload_bytes(result_rel, buffer.getvalue())

    image_id = save_analysis_and_detections(
        meta, original_rel, result_rel, class_counts, created_at
    )
    return image_id, original_rel, result_rel


def render_db_save_section(result: InferenceResult, meta: Optional[Dict[str, Any]]) -> None:
    """image_analysis·detection_result에 저장될 내용을 미리 보여주고, 버튼 하나로 함께 저장한다.

    검토 레일 카드 안의 소섹션으로 그린다 (별도 카드가 아니라 구분선 + 소제목).
    """
    with st.container(key="rail_eosar_database"):
        st.html(
            '<div class="ui-rail-divider" aria-hidden="true"></div>'
            '<div class="ui-rail-heading">분석 결과 저장<small>DATABASE</small></div>'
        )

        if meta is None:
            st.info(
                f"파일명 '{result.filename}'이 저장 형식이 아니어서 DB 저장은 할 수 없습니다. "
                "형식: 자산명_지역명_지역ID_센서_YYYY-MM-DD 시각 "
                "(예: 425-1_개풍군_1_EO_2023-12-30 220000.png — 시각 앞은 공백/밑줄 모두 허용)"
            )
            return

        equipment_ctx = _load_equipment_ids()
        if equipment_ctx["error"]:
            st.warning(f"DB 연결 실패: {equipment_ctx['error']}")
            return

        # 같은 영상이 이미 등록돼 있으면 그 image_id를 미리 보여준다 (경로 미리보기에도 사용).
        try:
            existing_id = _find_existing_image_id(meta)
        except Exception:
            existing_id = None

        # 경로는 SAR/EO 페이지와 같은 규칙: 파일명이 그대로 S3 키가 된다.
        original_rel, result_rel = image_paths_for(result.filename)

        # 1) image_analysis에 저장될 내용 미리보기 (image_id는 DB가 자동 부여하므로 표시하지 않음).
        #    오른쪽 열은 폭이 좁으므로 항목을 세로로 보여준다.
        with st.expander("image_analysis에 저장될 내용", expanded=False):
            st.dataframe(
                pd.DataFrame(
                    [
                        {"항목": "자산", "값": meta["asset_name"]},
                        {"항목": "지역", "값": meta["region_name"]},
                        {"항목": "region_id", "값": str(meta["region_id"])},
                        {"항목": "센서", "값": meta["sensor_type"]},
                        {"항목": "촬영시각", "값": str(meta["captured_time"])},
                        {"항목": "original_image_path", "값": original_rel},
                        {"항목": "result_image_path", "값": result_rel},
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

        # 2) detection_result에 저장될 집계 미리보기 — 최종 검출목록(편집 반영) 기준.
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

        if existing_id is not None:
            st.caption(
                f"이미 등록된 영상입니다 (image_id={existing_id}). "
                "저장하면 같은 image_id의 경로·탐지 결과를 덮어씁니다."
            )

        # 3) 저장 버튼 하나로 결과 이미지 업로드 + 두 테이블을 함께 저장한다.
        if st.button("DB 저장", type="primary", use_container_width=True, key="eosar_db_save"):
            created_at = datetime.now()   # 버튼을 누른 시스템 시간을 created_at으로 기록
            rows = [(equipment[label], cnt) for label, cnt in sorted(matched.items())]
            annotated = draw_boxes(result.scene, result.detections)   # 편집 반영된 최종 박스
            try:
                image_id, saved_original, saved_result = _save_all(
                    meta,
                    result.filename,
                    annotated,
                    rows,
                    created_at,
                )
                outcome = analyze_image_change(image_id)
            except Exception as exc:
                st.error(f"DB 저장 실패: {exc}")
            else:
                st.session_state[_SESSION_SAVED_NAME_KEY] = result.filename
                st.success(
                    f"저장 완료: image_id={image_id} (자동 부여), "
                    f"detection_result {len(rows)}개 클래스, "
                    f"원본 → {saved_original}, 결과 → {saved_result} "
                    f"({created_at:%Y-%m-%d %H:%M:%S})"
                )
                render_change_analysis_result(outcome)


# =====================================================================
# 3.5) 보고서 — 저장된 영상의 분석 보고서(HTML)를 이 화면에서 바로 다운로드
# =====================================================================

def _report_bytes_for(image_id: int) -> Tuple[str, bytes]:
    """image_id의 분석 보고서 HTML을 만들어 (파일명, 파일 내용)으로 돌려준다.

    조회·양식은 Reports 페이지 모듈을 재사용하고, 결과 이미지는 S3에서 받아
    (로컬 캐시) base64로 임베드한다 — 보고서 파일 하나로 어디서든 열리게.
    """
    info = reports_repository.fetch_image_detail(image_id)
    if info is None:
        raise ValueError(f"image_id={image_id} 영상을 찾을 수 없습니다.")
    detections = reports_repository.fetch_detections(image_id)

    image_b64 = None
    local = s3_store.ensure_local(str(info.get("result_image_path") or ""))
    if local is not None:
        image_b64 = base64.b64encode(local.read_bytes()).decode("ascii")

    html = analysis_report.build_analysis_report(info, detections, image_b64)
    return f"분석보고서_{image_id}.html", html.encode("utf-8")


def _past_image_label(row: Dict[str, Any]) -> str:
    """과거 분석 목록 selectbox에 보여줄 한 줄 요약."""
    return (
        f"#{row['image_id']} · {row['asset_name']} · {row['region_name']} · "
        f"{row['sensor_type']} · {row['captured_time']}"
    )


def render_report_section(meta: Optional[Dict[str, Any]]) -> None:
    """보고서 카드: 현재 영상 보고서 다운로드 + 과거 분석 보고서 선택 다운로드.

    보고서는 DB 데이터로 생성하므로, 현재 영상은 'DB 저장 후'에만 활성화된다
    (편집 중인 미확정 검출 목록과 보고서 내용이 어긋나는 것을 막기 위함).
    """
    with st.container(key="rail_eosar_report"):
        st.html(
            '<div class="ui-rail-divider" aria-hidden="true"></div>'
            '<div class="ui-rail-heading">분석 보고서<small>REPORT</small></div>'
        )

        # 1) 현재 영상 — 저장돼 있어야(image_id 존재) 생성 가능.
        image_id: Optional[int] = None
        if meta is not None:
            try:
                image_id = _find_existing_image_id(meta)
            except Exception:
                image_id = None

        if image_id is None:
            st.button(
                "현재 영상 보고서 다운로드", disabled=True, type="primary",
                use_container_width=True, key="eosar_report_current_disabled",
            )
            st.caption("DB 저장 후 생성할 수 있습니다.")
        else:
            try:
                file_name, data = _report_bytes_for(image_id)
            except Exception as exc:
                st.warning(f"보고서 생성 실패: {exc}")
            else:
                st.download_button(
                    "현재 영상 보고서 다운로드",
                    data=data, file_name=file_name, mime="text/html", type="primary",
                    use_container_width=True, key="eosar_report_current",
                )

        # 2) 과거 분석 — 최근 영상 목록에서 골라 그 시점 DB 기준으로 재생성.
        with st.expander("과거 분석 보고서", expanded=False):
            try:
                items = reports_repository.fetch_image_list(None, 200)
            except Exception as exc:
                st.warning(f"과거 분석 목록 조회 실패: {exc}")
                items = []

            selected = st.selectbox(
                "영상 선택 (최근 200건)",
                options=items,
                index=None,
                placeholder="보고서를 만들 영상을 선택하세요",
                format_func=_past_image_label,
                key="eosar_report_past_select",
            )
            if selected is not None:
                try:
                    file_name, data = _report_bytes_for(int(selected["image_id"]))
                except Exception as exc:
                    st.warning(f"보고서 생성 실패: {exc}")
                else:
                    st.download_button(
                        "선택 영상 보고서 다운로드",
                        data=data, file_name=file_name, mime="text/html", type="primary",
                        use_container_width=True, key="eosar_report_past",
                    )


# =====================================================================
# 4) 결과 표시 — 검출 목록의 선택/수정/삭제/추가는 기존 두 페이지와 동일
# =====================================================================

def render_run_summary(result: InferenceResult, sensor: str) -> None:
    """실행 완료 후 센서·소요 시간·탐지 수(SAR은 회전·방위각까지)를 한 줄로 보여준다."""
    items = [
        InfoItem("센서", sensor, "primary"),
        InfoItem("처리 시간", f"{result.elapsed_sec}s", "success"),
        InfoItem("탐지 결과", f"{len(result.detections)}개"),
    ]
    if sensor == "SAR":
        items.append(
            InfoItem(
                "영상 회전",
                f"{result.rotate_deg}도 ({'자동' if result.auto_rotation else '수동'})",
            )
        )
        if result.azimuth is not None:
            items.append(InfoItem("방위각", f"{result.azimuth}도"))
    render_info_strip(items, compact=True)


def render_detection_table(rows: List[Dict], sensor: str) -> List[int]:
    """탐지된 표적 목록을 보여주고, 선택된 행의 라벨/박스 편집 UI를 제공한다."""
    # 기본은 접힌 상태 — 레일을 짧게 유지하고, 편집할 때만 펼쳐 쓴다.
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
                key="eosar_detection_table",
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

        _render_add_detection_form(rows, sensor)
        return selected_indices


def _render_detection_editor(rows: List[Dict], selected_idx: int) -> None:
    """선택한 detection의 label/bbox를 수정하는 작은 폼을 그린다."""
    selected = rows[selected_idx]
    x1, y1, x2, y2 = [float(value) for value in selected["bbox"]]

    with st.form(key=f"eosar_detection_editor_{selected_idx}"):
        edited_label = st.text_input(
            "label",
            value=str(selected["label"]),
            key=f"eosar_detection_label_{selected_idx}",
        )
        coord_cols = st.columns(4)
        with coord_cols[0]:
            edited_x1 = st.number_input(
                "x1",
                value=x1,
                step=1.0,
                format="%.1f",
                key=f"eosar_detection_x1_{selected_idx}",
            )
        with coord_cols[1]:
            edited_y1 = st.number_input(
                "y1",
                value=y1,
                step=1.0,
                format="%.1f",
                key=f"eosar_detection_y1_{selected_idx}",
            )
        with coord_cols[2]:
            edited_x2 = st.number_input(
                "x2",
                value=x2,
                step=1.0,
                format="%.1f",
                key=f"eosar_detection_x2_{selected_idx}",
            )
        with coord_cols[3]:
            edited_y2 = st.number_input(
                "y2",
                value=y2,
                step=1.0,
                format="%.1f",
                key=f"eosar_detection_y2_{selected_idx}",
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


def _render_add_detection_form(rows: List[Dict], sensor: str) -> None:
    """사용자가 새 detection 행을 추가하는 폼을 그린다 (미탐 객체를 직접 박스 치는 용도).

    라벨 입력 방식은 각 센서의 기존 페이지와 같다: EO는 선택 목록, SAR은 직접 입력.
    검출 목록이 expander로 바뀌면서 (expander 중첩 불가) 이 폼은 popover로 연다.
    """
    with st.popover("새 박스 추가", use_container_width=True):
        with st.form("eosar_add_detection_form"):
            if sensor == "EO":
                new_label = st.selectbox("label", options=_EO_LABELS)
            else:
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

    new_row: Dict[str, Any] = {
        "label": (new_label.strip() or "New") if sensor == "SAR" else new_label,
        "bbox": _normalize_bbox([new_x1, new_y1, new_x2, new_y2]),
    }
    # 신뢰도 키는 센서별 기존 형식을 따라 채워둔다 (표시는 라벨만 사용).
    if sensor == "EO":
        new_row["conf"] = None
    else:
        new_row["det_conf"] = None
        new_row["cls_conf"] = None
    rows.append(new_row)
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


def render_image_panel(result: InferenceResult, selected_indices: List[int]) -> None:
    """왼쪽 이미지 카드: 파일명과 박스가 그려진 탐지 이미지를 보여준다."""
    with st.container(key="panel_eosar_image_result"):
        render_section_header("탐지 결과", f"파일: {result.filename}", badge="RESULT")
        selected_detections = _detections_for_selection(result.detections, selected_indices)
        st.image(draw_boxes(result.scene, selected_detections), use_container_width=True)
        if selected_indices:
            st.caption("선택한 행의 박스만 표시 중입니다. 표 선택을 해제하면 전체 박스가 표시됩니다.")


def render_placeholder_panel() -> None:
    """아직 실행한 결과가 없을 때 왼쪽에 ARGOS 로고와 안내 문구를 보여준다."""
    with st.container(key="panel_eosar_image_empty"):
        render_section_header(
            "영상 작업영역",
            "원본과 탐지 결과가 동일한 작업영역에 표시됩니다.",
            badge="WORKSPACE",
        )
        render_empty_state(
            "판독할 영상을 선택하세요",
            "오른쪽 원본 목록에서 파일을 선택하면 미리보기가 열리고, 실행 후 탐지 결과로 전환됩니다.",
            symbol="◎",
        )


def _render_original_preview(filename: Optional[str], s3_key: str) -> None:
    """파일을 골라둔(아직 실행 전) 상태에서 왼쪽에 원본 이미지를 미리 보여준다.

    S3에서 받아(로컬 캐시 재사용) 표시한다. TIF 등 브라우저가 직접 못 여는 형식도
    PIL로 열어서 넘기므로 문제없다.
    """
    with st.container(key="panel_eosar_image_preview"):
        render_section_header(
            "원본 미리보기",
            f"{filename} · 실행 후 탐지 결과로 전환됩니다.",
            badge="PREVIEW",
        )
        local = s3_store.ensure_local(s3_key)
        if local is None:
            st.warning("S3에서 원본을 받지 못했습니다. 목록을 새로고침해 보세요.")
            return
        try:
            from PIL import Image

            image = Image.open(local)
            image.load()
            if image.mode not in ("RGB", "RGBA", "L"):
                image = image.convert("RGB")   # 16비트 TIF 등은 표시 가능한 모드로 변환
            st.image(image, use_container_width=True)
        except Exception as exc:
            st.warning(f"원본 미리보기 실패: {exc}")


# =====================================================================
# 5) 세션 상태 — DB 저장 버튼 클릭(rerun) 후에도 결과를 유지한다
# =====================================================================

def _save_result(
    result: InferenceResult,
    sensor: str,
    upload_name: Optional[str],
    file_bytes: bytes,
) -> None:
    """행 선택·DB 저장 등 rerun 이후에도 쓸 수 있게 마지막 추론 결과·센서·원본 바이트를 저장한다."""
    st.session_state[_SESSION_RESULT_KEY] = result
    st.session_state[_SESSION_SENSOR_KEY] = sensor
    st.session_state[_SESSION_UPLOAD_NAME_KEY] = upload_name
    st.session_state[_SESSION_FILE_BYTES_KEY] = file_bytes


def _clear_saved_result() -> None:
    """파일이 바뀌거나 실패했을 때 이전 추론 결과를 지운다."""
    for key in [
        _SESSION_RESULT_KEY,
        _SESSION_SENSOR_KEY,
        _SESSION_UPLOAD_NAME_KEY,
        _SESSION_FILE_BYTES_KEY,
        _SESSION_FLASH_KEY,
    ]:
        st.session_state.pop(key, None)


def _sync_saved_result_with_upload(controls: EosarControls) -> None:
    """선택한 파일이 바뀌었는데 새 실행 전이라면 이전 결과를 숨긴다."""
    saved_upload_name = st.session_state.get(_SESSION_UPLOAD_NAME_KEY)
    if not controls.run_clicked and controls.filename != saved_upload_name:
        _clear_saved_result()


# =====================================================================
# 6) 페이지 진입점 — 메인 작업영역 + 하단 저장·보고 영역
# =====================================================================

def render_eosar_page() -> None:
    """EO/SAR 통합 탐지 페이지 전체를 그린다: 입력 받기 → 센서별 추론 → 결과 표시 → DB 저장.

    배치: 왼쪽은 고정 높이 영상 뷰어, 오른쪽은 검토 → DB 저장 → 보고서로 이어지는
    워크플로 레일. 판독 업무가 위에서 아래로 한 열에서 끝난다.
    """
    _render_header()
    _render_workflow_row()

    controls = render_controls()
    _sync_saved_result_with_upload(controls)

    image_col, review_col = st.columns([0.63, 0.37], gap="large")

    error_message: Optional[str] = None
    if controls.run_clicked:
        if controls.filename is None or controls.s3_key is None:
            error_message = "S3 원본 목록에서 이미지를 선택하세요."
        else:
            sensor = controls.meta["sensor_type"]
            with image_col:
                with st.spinner(f"{sensor} 모델로 추론 중입니다. CPU 환경에서는 시간이 걸릴 수 있습니다."):
                    try:
                        # 원본을 S3에서 받아온다 (로컬 캐시에 있으면 그대로 재사용).
                        local = s3_store.ensure_local(controls.s3_key)
                        if local is None:
                            raise RuntimeError(f"S3에서 원본을 받지 못했습니다: {controls.s3_key}")
                        file_bytes = local.read_bytes()
                        if sensor == "EO":
                            result = eo_service.run_inference(file_bytes, controls.filename)
                        else:
                            result = sar_service.run_inference(
                                file_bytes, controls.filename, controls.rotate_k
                            )
                    except (eo_service.ModelUnavailableError, sar_service.ModelUnavailableError) as exc:
                        _clear_saved_result()
                        error_message = str(exc)
                    except Exception as exc:
                        _clear_saved_result()
                        error_message = f"추론 실패: {exc}"
                    else:
                        _save_result(result, sensor, controls.filename, file_bytes)
                        # 상단 워크플로 바(이미 그려짐)에 완료 상태가 바로 반영되도록
                        # 결과를 세션에 담고 한 번 다시 그린다.
                        st.session_state[_SESSION_FLASH_KEY] = (
                            f"분석 완료 — {len(result.detections)}개 표적을 탐지했습니다."
                        )
                        st.rerun()

    result: Optional[InferenceResult] = st.session_state.get(_SESSION_RESULT_KEY)
    sensor: Optional[str] = st.session_state.get(_SESSION_SENSOR_KEY)

    # 검출 목록 선택 결과를 왼쪽 이미지에 반영해야 하므로 검토 카드를 먼저 그린다.
    selected_indices: List[int] = []
    meta = parse_image_meta(result.filename) if result is not None else None
    with review_col:
        with st.container(key="panel_eosar_review"):
            render_section_header(
                "검출 결과 검토",
                "탐지된 표적과 경계상자를 확인하고 필요한 경우 수정합니다.",
                badge="REVIEW",
            )
            if error_message:
                st.warning(error_message)
            if result is not None and sensor is not None:
                render_run_summary(result, sensor)
                flash_message = st.session_state.pop(_SESSION_FLASH_KEY, None)
                if flash_message:
                    st.success(flash_message)
                selected_indices = render_detection_table(result.detections, sensor)
                # 저장과 보고서는 같은 카드 안 소섹션으로 이어 붙인다 — 오른쪽이
                # 카드 하나로 끝나 왼쪽 뷰어 카드와 아래끝이 맞는다.
                render_db_save_section(result, meta)
                render_report_section(meta)
            else:
                render_empty_state(
                    "분석 결과 대기",
                    "상단에서 원본을 선택하고 분석을 실행하면 탐지 요약과 검출 목록이 표시됩니다.",
                    symbol="03",
                )

    # 왼쪽 열: 실행 후에는 탐지 결과 이미지, 파일만 골라둔 상태면 원본 미리보기,
    # 아무것도 선택 안 했으면 빈 작업영역 안내.
    with image_col:
        if result is not None and sensor is not None:
            render_image_panel(result, selected_indices)
        elif controls.s3_key is not None:
            _render_original_preview(controls.filename, controls.s3_key)
        else:
            render_placeholder_panel()
