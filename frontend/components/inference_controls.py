from dataclasses import dataclass
from typing import Any, Optional

import streamlit as st

from core.settings import DEFAULT_BACKEND_URL
from services.sar_api import SarApiClient, SarApiError


@dataclass
class InferenceControls:
    client: SarApiClient
    tif_file: Optional[Any]
    rotate_k: int
    run_clicked: bool


def render_inference_controls() -> InferenceControls:
    st.subheader("입력")
    settings_col, upload_col, action_col = st.columns(
        [1.2, 1.6, 1.0],
        vertical_alignment="bottom",
    )

    with settings_col:
        backend_url = st.text_input("백엔드 URL", value=DEFAULT_BACKEND_URL)
        with st.expander("수동 회전 (방위각이 없을 때 적용)", expanded=False):
            manual_rot = st.select_slider(
                "회전 각도",
                options=[0, 90, 180, 270],
                value=0,
                format_func=lambda value: f"{value}도",
            )
            rotate_k = manual_rot // 90

    client = SarApiClient(backend_url)
    with upload_col:
        tif_file = st.file_uploader(
            "이미지 업로드 (TIF / PNG / JPG)",
            type=["tif", "tiff", "png", "jpg", "jpeg"],
        )

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
