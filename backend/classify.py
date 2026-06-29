from typing import List, Tuple

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image

from backend import models as _m

# ── 분류 transform (노트북과 동일 — Normalize 없음) ───────────────
_cls_transform = T.Compose([
    T.Resize((128, 128)),
    T.Grayscale(num_output_channels=3),
    T.ToTensor(),
])


def _extract_chip(scene_rgb: np.ndarray, box: List[float], win: int = 128) -> Image.Image:
    H, W = scene_rgb.shape[:2]
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    left = int(min(max(cx - win / 2, 0), max(W - win, 0)))
    top  = int(min(max(cy - win / 2, 0), max(H - win, 0)))
    return Image.fromarray(scene_rgb[top:top + win, left:left + win])


def classify_boxes_batch(
    scene_rgb: np.ndarray,
    boxes: List[List[float]],
    win: int = 128,
) -> List[Tuple[str, float]]:
    """여러 박스를 배치로 한 번에 분류. boxes가 비면 빈 리스트 반환."""
    if not boxes:
        return []
    chips = [_cls_transform(_extract_chip(scene_rgb, b, win)) for b in boxes]
    batch = torch.stack(chips)          # (N, 3, 128, 128)
    with torch.no_grad():
        probs = torch.softmax(_m._classifier(batch), dim=1)
    return [(_m._class_names[int(p.argmax())], float(p.max())) for p in probs]


def classify_box(scene_rgb: np.ndarray, box: List[float], win: int = 128) -> Tuple[str, float]:
    """단일 박스 분류 (배치 함수 래퍼)."""
    return classify_boxes_batch(scene_rgb, [box], win)[0]
