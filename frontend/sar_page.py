"""
[프론트엔드 - 추론 화면 (하나로 합친 파일)]
사용자가 실제로 보는 SAR 추론 페이지. 원래 입력 컨트롤/결과 표시로 나뉘어 있던 것을
초보자가 화면 흐름을 위→아래로 따라갈 수 있도록 한 파일에 모아두었다.

읽는 순서(위→아래):
  1) 입력 컨트롤   : 백엔드 주소·회전 설정·파일 업로드·실행 버튼을 그린다
  2) 결과 표시     : 백엔드가 준 탐지 결과를 요약·이미지·표로 보여준다
  3) 페이지 진입점 : 위 둘을 이어 붙여, 실행 버튼을 누르면 백엔드를 호출하고 결과를 그린다
"""
import io
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from sar_api import SarApiClient, SarApiError
from settings import DEFAULT_BACKEND_URL
from viz import draw_boxes, load_scene_for_vis


# =====================================================================
# 1) 입력 컨트롤 — 화면 위쪽 입력 영역
# =====================================================================

@dataclass
class InferenceControls:
    """입력 영역에서 사용자가 고른 값들을 한 꾸러미로 담아 전달한다."""
    client: SarApiClient
    tif_file: Optional[Any]
    rotate_k: int
    run_clicked: bool


def render_inference_controls() -> InferenceControls:
    """회전·파일 업로드·실행 버튼을 그리고, 사용자가 고른 값을 돌려준다."""
    st.subheader("입력")
    settings_col, upload_col, action_col = st.columns(
        [1.2, 1.6, 1.0],
        vertical_alignment="bottom",
    )

    # 왼쪽: (방위각이 없을 때 쓰는) 수동 회전 선택
    with settings_col:
        with st.expander("수동 회전 (방위각이 없을 때 적용)", expanded=False):
            manual_rot = st.select_slider(
                "회전 각도",
                options=[0, 90, 180, 270],
                value=0,
                format_func=lambda value: f"{value}도",
            )
            rotate_k = manual_rot // 90   # 각도(0/90/180/270)를 회전 횟수(0/1/2/3)로 변환

    client = SarApiClient(DEFAULT_BACKEND_URL)
    # 가운데: 이미지 업로드
    with upload_col:
        tif_file = st.file_uploader(
            "이미지 업로드 (TIF / PNG / JPG)",
            type=["tif", "tiff", "png", "jpg", "jpeg"],
        )

    # 오른쪽: 모델 로드 상태 표시 + 실행 버튼
    with action_col:
        try:
            health = client.health()
            if health.get("models_loaded"):
                st.success("모델 로드됨")
            else:
                st.error(f"모델 미로드: {health.get('error', '')}")
        except SarApiError as exc:
            st.warning(str(exc))
        run_clicked = st.button("실행", type="primary", use_container_width=True)

    st.divider()

    return InferenceControls(
        client=client,
        tif_file=tif_file,
        rotate_k=rotate_k,
        run_clicked=run_clicked,
    )


# =====================================================================
# 2) 결과 표시 — 백엔드 응답을 화면에 그린다
# =====================================================================

def render_detection_table(rows: List[Dict]) -> None:
    """탐지된 차량 목록을 표(라벨·확신도·좌표)로 보여준다. 없으면 안내 문구."""
    if not rows:
        st.info("탐지된 차량이 없습니다.")
        return

    st.subheader(f"검출 목록 ({len(rows)}개)")
    dataframe = pd.DataFrame(
        [
            {
                "label": item["label"],
                "det_conf": round(item["det_conf"], 3) if item.get("det_conf") is not None else None,
                "cls_conf": round(item["cls_conf"], 3) if item.get("cls_conf") is not None else None,
            }
            for item in rows
        ]
    )
    st.dataframe(dataframe, use_container_width=True, hide_index=True)


def render_inference_result(result: Dict, scene_rgb: np.ndarray, elapsed_client: float) -> None:
    """추론 결과를 요약 줄 → (왼쪽) 박스 그린 이미지 · (오른쪽) 검출 표로 그린다."""
    detections = result["detections"]

    # 상단 요약: 소요 시간·탐지 개수·회전·방위각
    summary = [
        f"완료 {result.get('elapsed_sec', elapsed_client)}s",
        f"탐지 {len(detections)}개",
        f"회전 {result['rotate_deg']}도 ({'자동' if result.get('auto_rotation') else '수동'})",
    ]
    if result.get("azimuth") is not None:
        summary.append(f"방위각 {result['azimuth']}도")
    st.success(" | ".join(summary))

    # 왼쪽: 탐지 이미지, 오른쪽: 검출 결과 표
    image_col, table_col = st.columns([2, 1])
    with image_col:
        st.subheader("탐지 결과")
        st.image(draw_boxes(scene_rgb, detections), use_container_width=True)
    with table_col:
        render_detection_table(detections)


# =====================================================================
# 3) 페이지 진입점 — 입력과 결과를 이어 붙인다
# =====================================================================

def render_inference_page() -> None:
    """추론 페이지 전체를 그린다: 입력 받기 → 실행 시 백엔드 호출 → 결과 표시."""
    st.title("DOM SAR 차량 탐지 데모")
    st.caption("YOLO11n + ConvNeXt-Tiny 기반 14종 차량 분류")

    controls = render_inference_controls()

    # 실행 버튼을 누르지 않았으면 여기서 멈춘다.
    if not controls.run_clicked:
        return

    if controls.tif_file is None:
        st.warning("이미지를 업로드하세요.")
        st.stop()

    tif_bytes = controls.tif_file.getvalue()

    # 백엔드에 추론을 요청한다 (CPU 환경에서는 시간이 걸릴 수 있음).
    with st.spinner("추론 중입니다. CPU 환경에서는 시간이 걸릴 수 있습니다."):
        started_at = time.time()
        try:
            result = controls.client.infer(
                tif_file=controls.tif_file,
                rotate_k=controls.rotate_k,
            )
        except SarApiError as exc:
            st.error(str(exc))
            st.stop()

    # 원본 이미지 위에 결과 박스를 그려 화면에 표시한다.
    scene = _scene_from_upload(tif_bytes, result)
    render_inference_result(result, scene, elapsed_client=round(time.time() - started_at, 1))


def _scene_from_upload(tif_bytes: bytes, result: dict) -> np.ndarray:
    """업로드 이미지를 화면 표시용으로 읽어온다. 실패하면 검은 배경으로 대체한다."""
    scene_rgb = load_scene_for_vis(io.BytesIO(tif_bytes))
    if scene_rgb is not None:
        return scene_rgb

    width, height = result["image_size"]
    return np.zeros((height, width, 3), dtype=np.uint8)
