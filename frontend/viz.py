from typing import List, Dict, Optional

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

STATUS_COLOR = {
    "correct": "#00FF00",
    "wrong":   "#FF3333",
    "fp":      "#FFFF00",
    "missed":  "#3399FF",
    "default": "#00FF00",
}


def draw_boxes(scene_rgb: np.ndarray, detections: List[Dict], use_status: bool) -> Image.Image:
    img = Image.fromarray(scene_rgb).convert("RGB")
    MAX_SIDE = 1200
    scale = 1.0
    if max(img.width, img.height) > MAX_SIDE:
        scale = MAX_SIDE / max(img.width, img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

    draw = ImageDraw.Draw(img)
    font_size = max(10, int(14 * scale))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    for det in detections:
        bx1, by1, bx2, by2 = [v * scale for v in det["bbox"]]
        status = det.get("status", "fp")
        color = STATUS_COLOR.get(status, STATUS_COLOR["fp"]) if use_status else STATUS_COLOR["default"]
        draw.rectangle([bx1, by1, bx2, by2], outline=color, width=max(1, int(2 * scale)))
        cc = det.get("cls_conf")
        if status == "missed":
            label = f"{det['label']} (미탐)"
        elif cc is None:
            label = str(det["label"])
        else:
            label = f"{det['label']} {cc:.2f}"
        try:
            tb = draw.textbbox((bx1, by1 - font_size - 2), label, font=font)
            draw.rectangle(tb, fill=(0, 0, 0, 180))
        except Exception:
            pass
        draw.text((bx1, by1 - font_size - 2), label, fill=color, font=font)

    return img


def metrics_card(metrics: Dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("GT 수",   str(metrics.get("n_gt", "-")))
    c2.metric("Recall",  f"{metrics.get('recall', 0):.3f}")
    c3.metric("Cls/Det", f"{metrics.get('cls_on_det', 0):.3f}")
    c4.metric("E2E",     f"{metrics.get('E2E', 0):.3f}")


def load_scene_for_vis(tif_path: str) -> Optional[np.ndarray]:
    """시각화용으로 로컬 TIF를 numpy 배열로 로드."""
    try:
        arr = np.array(Image.open(tif_path))
        if arr.dtype != np.uint8:
            a = arr.astype(np.float32)
            p = np.percentile(a[a > 0], 99) if (a > 0).any() else 1.0
            arr = np.clip(a / (p + 1e-9) * 255, 0, 255).astype(np.uint8)
        if arr.ndim == 3:
            arr = arr[..., 0]
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=-1)
        return arr
    except Exception:
        return None
