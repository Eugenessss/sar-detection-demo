"""
[Reports 도메인 - 화면]
image_analysis에 등록된 영상을 최신(image_id 내림차순)부터 훑어보고,
행을 클릭하면 상세 정보·탐지 집계·결과 이미지를 보여주며
분석 보고서(.html)를 만들어 내려받을 수 있는 페이지.
흐름: 필터(센서·개수) → 목록 표 → 행 선택 → 상세 + 결과 이미지 + [보고서 다운로드].
조회는 reports/repository.py를, 보고서 작성은 reports/report.py를 직접 부른다.
"""
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from features.reports import report, repository
from shared import s3_store

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RESULT_DIR = _PROJECT_ROOT / "result_image"


# =====================================================================
# 1) 조회 (rerun마다 DB를 다시 두드리지 않게 짧은 캐시를 둔다)
# =====================================================================

@st.cache_data(ttl=30, show_spinner=False)
def _load_image_list(sensor: Optional[str], limit: int) -> Dict[str, Any]:
    """영상 목록을 조회한다 (실패해도 화면이 죽지 않게 error로 전달)."""
    try:
        return {"rows": repository.fetch_image_list(sensor, limit), "error": None}
    except Exception as exc:
        return {"rows": [], "error": str(exc)}


@st.cache_data(ttl=30, show_spinner=False)
def _load_image_detail(image_id: int) -> Dict[str, Any]:
    """선택한 영상의 상세와 탐지 집계를 함께 조회한다."""
    try:
        return {
            "info": repository.fetch_image_detail(image_id),
            "detections": repository.fetch_detections(image_id),
            "error": None,
        }
    except Exception as exc:
        return {"info": None, "detections": [], "error": str(exc)}


def _find_result_image(info: Dict[str, Any]) -> Optional[Path]:
    """결과 이미지 파일을 찾는다.

    1순위: DB의 result_image_path가 가리키는 파일 (로컬에 없으면 S3에서 내려받음)
    2순위: result_image/{image_id}.* (eosar 페이지가 image_id 이름으로 저장)
    둘 다 없으면 None.
    """
    recorded = str(info.get("result_image_path") or "").strip()
    if recorded:
        found = s3_store.ensure_local(recorded)
        if found is not None:
            return found

    for candidate in sorted(_RESULT_DIR.glob(f"{info['image_id']}.*")):
        if candidate.is_file():
            return candidate
    return None


# =====================================================================
# 2) 화면 구성
# =====================================================================

def _render_filters() -> Dict[str, Any]:
    """센서·표시 개수 필터를 그리고 선택값을 돌려준다."""
    sensor_col, limit_col, _pad = st.columns([1.0, 1.0, 2.0])
    with sensor_col:
        sensor_label = st.selectbox("센서", ["전체", "EO", "SAR"])
    with limit_col:
        limit = st.selectbox("표시 개수", [50, 100, 300], index=1)
    return {
        "sensor": None if sensor_label == "전체" else sensor_label,
        "limit": int(limit),
    }


def _render_image_table(rows: List[Dict[str, Any]]) -> Optional[int]:
    """영상 목록 표를 그리고, 선택된 행의 image_id를 돌려준다 (선택 없으면 None)."""
    dataframe = pd.DataFrame(
        [
            {
                "image_id": row["image_id"],
                "자산": row["asset_name"],
                "지역": row["region_name"],
                "센서": row["sensor_type"],
                "촬영시각": row["captured_time"],
                "등록시각": row["created_at"],
            }
            for row in rows
        ]
    )
    event = st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        height=350,
        key="reports_image_table",
        on_select="rerun",
        selection_mode="single-row",
    )

    selection = getattr(event, "selection", {})
    if isinstance(selection, dict):
        selected_rows = list(selection.get("rows", []))
    else:
        selected_rows = list(getattr(selection, "rows", []))
    if not selected_rows:
        return None
    selected_idx = selected_rows[0]
    if not (0 <= selected_idx < len(rows)):
        return None
    return int(rows[selected_idx]["image_id"])


def _render_detail(image_id: int) -> None:
    """선택한 영상의 상세 정보·탐지 집계·결과 이미지·보고서 다운로드를 그린다."""
    detail = _load_image_detail(image_id)
    if detail["error"]:
        st.warning(f"상세 조회 실패: {detail['error']}")
        return
    info = detail["info"]
    if info is None:
        st.warning(f"image_id={image_id} 영상을 찾을 수 없습니다 (목록 갱신 필요).")
        return
    detections = detail["detections"]

    with st.container(border=True):
        st.subheader(f"영상 상세 — image_id {image_id}")

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "자산": info["asset_name"],
                        "지역": info["region_name"],
                        "센서": info["sensor_type"],
                        "촬영시각": info["captured_time"],
                        "등록시각": info["created_at"],
                    }
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

        image_col, table_col = st.columns([1.4, 1.0])

        # 결과 이미지 (있을 때만)
        image_path = _find_result_image(info)
        result_image_b64: Optional[str] = None
        with image_col:
            st.caption("탐지 결과 이미지")
            if image_path is not None:
                image_bytes = image_path.read_bytes()
                result_image_b64 = base64.b64encode(image_bytes).decode("ascii")
                st.image(image_bytes, use_container_width=True)
            else:
                st.info("결과 이미지가 없습니다 (보고서는 텍스트만 포함됩니다).")

        # 탐지 집계 표
        with table_col:
            st.caption("탐지 결과")
            if detections:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "장비": det["class_name"],
                                "위협등급": det["threat_level"],
                                "탐지 수": det["detected_count"],
                            }
                            for det in detections
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("저장된 탐지 결과가 없습니다.")

        # 보고서는 문자열 생성이라 가벼우므로 미리 만들어 다운로드 버튼에 바로 물린다.
        html = report.build_analysis_report(info, detections, result_image_b64)
        st.download_button(
            "분석 보고서 다운로드 (.html)",
            data=html,
            file_name=f"analysis_report_{image_id}.html",
            mime="text/html",
            use_container_width=True,
            type="primary",
        )


# =====================================================================
# 3) 페이지 진입점
# =====================================================================

def render_reports_page() -> None:
    """Reports 페이지 전체를 그린다: 목록 조회 → 행 선택 → 상세 + 보고서."""
    st.title("영상 분석 보고서")
    st.caption("등록된 영상을 최신순으로 조회하고, 선택한 영상의 분석 보고서를 생성합니다")

    filters = _render_filters()
    listing = _load_image_list(filters["sensor"], filters["limit"])

    if listing["error"]:
        st.error(f"목록 조회 실패: {listing['error']}")
        return
    rows = listing["rows"]
    if not rows:
        st.info("등록된 영상이 없습니다.")
        return

    st.caption(f"최신 {len(rows)}개 (image_id 내림차순) — 행을 클릭하면 상세와 보고서가 표시됩니다.")
    selected_image_id = _render_image_table(rows)

    if selected_image_id is not None:
        _render_detail(selected_image_id)
