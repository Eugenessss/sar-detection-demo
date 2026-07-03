from typing import List, Tuple

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image

from backend.sar import models as _m

_cls_transform = T.Compose(
    [
        T.Resize((128, 128)),
        T.Grayscale(num_output_channels=3),
        T.ToTensor(),
    ]
)


def _extract_chip(scene_rgb: np.ndarray, box: List[float], win: int = 128) -> Image.Image:
    height, width = scene_rgb.shape[:2]
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    left = int(min(max(cx - win / 2, 0), max(width - win, 0)))
    top = int(min(max(cy - win / 2, 0), max(height - win, 0)))
    return Image.fromarray(scene_rgb[top:top + win, left:left + win])


def classify_boxes_batch(
    scene_rgb: np.ndarray,
    boxes: List[List[float]],
    win: int = 128,
) -> List[Tuple[str, float]]:
    """Classify multiple boxes in one batch."""
    if not boxes:
        return []

    chips = [_cls_transform(_extract_chip(scene_rgb, box, win)) for box in boxes]
    batch = torch.stack(chips)
    with torch.no_grad():
        probs = torch.softmax(_m.get_classifier()(batch), dim=1)

    class_names = _m.get_class_names()
    return [(class_names[int(prob.argmax())], float(prob.max())) for prob in probs]


def classify_box(scene_rgb: np.ndarray, box: List[float], win: int = 128) -> Tuple[str, float]:
    return classify_boxes_batch(scene_rgb, [box], win)[0]
