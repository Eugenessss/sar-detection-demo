import io
import time

import numpy as np
import streamlit as st

from components.inference_controls import render_inference_controls
from components.result_view import render_inference_result
from services.sar_api import SarApiError
from utils.viz import load_scene_for_vis


def render_inference_page() -> None:
    st.title("DOM SAR 차량 탐지 데모")
    st.caption("YOLO11n + ConvNeXt-Tiny 기반 14종 차량 분류")

    controls = render_inference_controls()

    if not controls.run_clicked:
        return

    if controls.tif_file is None:
        st.warning("이미지를 업로드하세요.")
        st.stop()

    tif_bytes = controls.tif_file.getvalue()

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

    scene = _scene_from_upload(tif_bytes, result)
    render_inference_result(result, scene, elapsed_client=round(time.time() - started_at, 1))


def _scene_from_upload(tif_bytes: bytes, result: dict) -> np.ndarray:
    scene_rgb = load_scene_for_vis(io.BytesIO(tif_bytes))
    if scene_rgb is not None:
        return scene_rgb

    width, height = result["image_size"]
    return np.zeros((height, width, 3), dtype=np.uint8)
