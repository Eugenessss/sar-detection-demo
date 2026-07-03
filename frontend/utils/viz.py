from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BOX_COLOR = "#00FF00"


def draw_boxes(scene_rgb: np.ndarray, detections: List[Dict]) -> Image.Image:
    img = Image.fromarray(scene_rgb).convert("RGB")
    max_side = 1200
    scale = 1.0
    if max(img.width, img.height) > max_side:
        scale = max_side / max(img.width, img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

    draw = ImageDraw.Draw(img)
    font_size = max(10, int(14 * scale))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    for det in detections:
        bx1, by1, bx2, by2 = [v * scale for v in det["bbox"]]
        draw.rectangle([bx1, by1, bx2, by2], outline=BOX_COLOR, width=max(1, int(2 * scale)))
        cls_conf = det.get("cls_conf")
        if cls_conf is None:
            label = str(det["label"])
        else:
            label = f"{det['label']} {cls_conf:.2f}"
        try:
            text_box = draw.textbbox((bx1, by1 - font_size - 2), label, font=font)
            draw.rectangle(text_box, fill=(0, 0, 0, 180))
        except Exception:
            pass
        draw.text((bx1, by1 - font_size - 2), label, fill=BOX_COLOR, font=font)

    return img


def load_scene_for_vis(image_source: Any) -> Optional[np.ndarray]:
    try:
        arr = np.array(Image.open(image_source))
        if arr.dtype != np.uint8:
            values = arr.astype(np.float32)
            percentile = np.percentile(values[values > 0], 99) if (values > 0).any() else 1.0
            arr = np.clip(values / (percentile + 1e-9) * 255, 0, 255).astype(np.uint8)
        if arr.ndim == 3:
            arr = arr[..., 0]
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=-1)
        return arr
    except Exception:
        return None
