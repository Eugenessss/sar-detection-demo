"""
[SAR 도메인 - 분류]
탐지 단계에서 찾은 박스 각각이 "어떤 종류의 차량인지" 14개 클래스 중 하나로 판별하는 단계.
박스 중심을 기준으로 작은 이미지 조각(chip)을 잘라 분류기(ConvNeXt)에 넣고,
가장 확률이 높은 클래스 이름과 그 확신도를 돌려준다.
"""
from typing import List, Tuple

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image

from backend.sar import models as _m

# 분류기에 넣기 전, 모든 조각을 동일한 형태(128x128, 3채널 텐서)로 맞추는 전처리 규칙.
_cls_transform = T.Compose(
    [
        T.Resize((128, 128)),
        T.Grayscale(num_output_channels=3),
        T.ToTensor(),
    ]
)


def _extract_chip(scene_rgb: np.ndarray, box: List[float], win: int = 128) -> Image.Image:
    """박스 중심을 기준으로 win×win 크기의 정사각형 이미지 조각을 잘라낸다."""
    height, width = scene_rgb.shape[:2]
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    # 조각이 이미지 밖으로 나가지 않도록 시작 좌표를 안쪽으로 눌러준다.
    left = int(min(max(cx - win / 2, 0), max(width - win, 0)))
    top = int(min(max(cy - win / 2, 0), max(height - win, 0)))
    return Image.fromarray(scene_rgb[top:top + win, left:left + win])


def classify_boxes_batch(
    scene_rgb: np.ndarray,
    boxes: List[List[float]],
    win: int = 128,
) -> List[Tuple[str, float]]:
    """여러 박스를 한 번에 분류해 [(클래스 이름, 확신도), ...] 형태로 돌려준다."""
    if not boxes:
        return []

    # 모든 박스에서 조각을 잘라 하나의 묶음(batch)으로 만들어 한 번에 분류한다.
    chips = [_cls_transform(_extract_chip(scene_rgb, box, win)) for box in boxes]
    batch = torch.stack(chips)
    with torch.no_grad():
        probs = torch.softmax(_m.get_classifier()(batch), dim=1)

    class_names = _m.get_class_names()
    return [(class_names[int(prob.argmax())], float(prob.max())) for prob in probs]


def classify_box(scene_rgb: np.ndarray, box: List[float], win: int = 128) -> Tuple[str, float]:
    """박스 하나만 분류하고 싶을 때 쓰는 편의 함수 (내부적으로 batch 함수를 재사용)."""
    return classify_boxes_batch(scene_rgb, [box], win)[0]
