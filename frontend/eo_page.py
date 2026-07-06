"""
[프론트엔드 - EO 탐지 화면]
사용자가 EO(일반 컬러 위성/항공 사진)를 올려 표적을 탐지하고 결과를 보는 페이지.
구조는 sar_page.py와 같다: 입력 컨트롤 → 백엔드 호출 → 결과(이미지+표) 표시.
SAR과 달리 컬러 사진이므로 원본 색 그대로 표시한 위에 박스를 그린다.
"""
import io
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from eo_api import EoApiClient, EoApiError
from settings import DEFAULT_BACKEND_URL
from viz import draw_boxes, load_image_rgb


# =====================================================================
# 1) 입력 컨트롤
# =====================================================================

@dataclass
class EoControls:
    """입력 영역에서 사용자가 고른 값들을 한 꾸러미로 담아 전달한다."""
    client: EoApiClient
    image_file: Optional[Any]
    run_clicked: bool


def render_eo_controls() -> EoControls:
    """파일 업로드·실행 버튼을 그리고, 사용자가 고른 값을 돌려준다."""
    st.subheader("입력")
    upload_col, action_col = st.columns(
        [2.0, 1.0],
        vertical_alignment="bottom",
    )

    client = EoApiClient(DEFAULT_BACKEND_URL)
    with upload_col:
        image_file = st.file_uploader(
            "이미지 업로드 (JPG / PNG / TIF)",
            type=["jpg", "jpeg", "png", "tif", "tiff"],
        )

    with action_col:
        # EO 모델이 로드됐는지 상태를 표시한다 (health 응답의 eo 항목 사용).
        try:
            health = client.health()
            eo_status = health.get("eo", {})
            if eo_status.get("models_loaded"):
                st.success("모델 로드됨")
            else:
                st.error(f"모델 미로드: {eo_status.get('error', '')}")
        except EoApiError as exc:
            st.warning(str(exc))
        run_clicked = st.button("실행", type="primary", use_container_width=True)

    st.divider()

    return EoControls(client=client, image_file=image_file, run_clicked=run_clicked)


# =====================================================================
# 2) 결과 표시
# =====================================================================

def render_detection_table(rows: List[Dict]) -> None:
    """탐지된 표적 목록을 표(클래스·신뢰도·좌표)로 보여준다. 없으면 안내 문구."""
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


def render_eo_result(result: Dict, scene_rgb: np.ndarray, elapsed_client: float) -> None:
    """추론 결과를 요약 줄 → (왼쪽) 박스 그린 이미지 · (오른쪽) 검출 표로 그린다."""
    detections = result["detections"]

    st.success(
        f"완료 {result.get('elapsed_sec', elapsed_client)}s | 탐지 {len(detections)}개"
    )

    # 왼쪽: 탐지 이미지, 오른쪽: 검출 결과 표
    image_col, table_col = st.columns([2, 1])
    with image_col:
        st.subheader("탐지 결과")
        st.image(draw_boxes(scene_rgb, detections), use_container_width=True)
    with table_col:
        render_detection_table(detections)


# =====================================================================
# 3) 페이지 진입점
# =====================================================================

def render_eo_page() -> None:
    """EO 탐지 페이지 전체를 그린다: 입력 받기 → 실행 시 백엔드 호출 → 결과 표시."""
    st.title("EO 표적 탐지")
    st.caption("YOLO 기반 EO(전자광학) 위성·항공 영상 표적 후보 탐지")

    controls = render_eo_controls()

    if not controls.run_clicked:
        return

    if controls.image_file is None:
        st.warning("이미지를 업로드하세요.")
        st.stop()

    image_bytes = controls.image_file.getvalue()

    with st.spinner("추론 중입니다. CPU 환경에서는 시간이 걸릴 수 있습니다."):
        started_at = time.time()
        try:
            result = controls.client.infer(image_file=controls.image_file)
        except EoApiError as exc:
            st.error(str(exc))
            st.stop()

    scene = _scene_from_upload(image_bytes, result)
    render_eo_result(result, scene, elapsed_client=round(time.time() - started_at, 1))


def _scene_from_upload(image_bytes: bytes, result: dict) -> np.ndarray:
    """업로드 이미지를 원본 색 그대로 읽어온다. 실패하면 검은 배경으로 대체한다."""
    scene_rgb = load_image_rgb(io.BytesIO(image_bytes))
    if scene_rgb is not None:
        return scene_rgb

    width, height = result["image_size"]
    return np.zeros((height, width, 3), dtype=np.uint8)
