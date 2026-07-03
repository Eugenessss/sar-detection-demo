from typing import Dict, List

import numpy as np
import pandas as pd
import streamlit as st

from utils.viz import draw_boxes


def render_inference_result(result: Dict, scene_rgb: np.ndarray, elapsed_client: float) -> None:
    detections = result["detections"]

    summary = [
        f"완료 {result.get('elapsed_sec', elapsed_client)}s",
        f"탐지 {len(detections)}개",
        f"회전 {result['rotate_deg']}도 ({'자동' if result.get('auto_rotation') else '수동'})",
    ]
    if result.get("azimuth") is not None:
        summary.append(f"방위각 {result['azimuth']}도")
    st.success(" | ".join(summary))

    st.subheader("탐지 결과")
    st.image(draw_boxes(scene_rgb, detections), use_container_width=True)

    render_detection_table(detections)


def render_detection_table(rows: List[Dict]) -> None:
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
                "x1": int(item["bbox"][0]),
                "y1": int(item["bbox"][1]),
                "x2": int(item["bbox"][2]),
                "y2": int(item["bbox"][3]),
            }
            for item in rows
        ]
    )
    st.dataframe(dataframe, use_container_width=True, hide_index=True)
