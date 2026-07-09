"""
[SAR 도메인 - 이미지 로딩/정규화]
SAR 이미지를 열어 밝기를 정규화하고 3채널 RGB 배열로 바꿔주는 파일.
SAR 원본은 밝기 범위가 제각각이라, 0~255로 맞추고 흑백을 3채널로 펼쳐줘야
모델(추론)과 화면(표시)이 다룰 수 있다.
  - normalize_to_uint8_rgb : 밝기 정규화 계산 (순수 numpy)
  - load_dom_rgb           : 추론 입력용 로딩 (파일 경로)
  - load_scene_for_vis     : 화면 표시용 로딩 (업로드 바이트 등, 실패하면 None)
(예전에는 백엔드·프론트가 나뉘어 있어 정규화만 shared/에 있었지만,
 통합 후 SAR 전용 로직이므로 이 파일에 모았다.)
"""
from typing import Any, Optional

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None   # 매우 큰 SAR 이미지도 열 수 있도록 픽셀 수 제한을 해제


def normalize_to_uint8_rgb(arr: np.ndarray) -> np.ndarray:
    """이미지 배열의 밝기를 0~255로 맞추고, 흑백이면 3채널 RGB로 펼쳐 돌려준다."""
    # 1) 이미 0~255(uint8)가 아니면, 상위 1% 밝기를 기준으로 스케일을 맞춘다.
    if arr.dtype != np.uint8:
        values = arr.astype(np.float32)
        positive_values = values[values > 0]
        percentile = np.percentile(positive_values, 99) if positive_values.size else 1.0
        arr = np.clip(values / (percentile + 1e-9) * 255, 0, 255).astype(np.uint8)

    # 2) 채널이 여러 개면 첫 채널만 쓰고, 흑백(2차원)이면 같은 값을 3번 쌓아 RGB로 만든다.
    if arr.ndim == 3:
        arr = arr[..., 0]
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)

    return arr


def load_dom_rgb(path: str) -> np.ndarray:
    """이미지 파일을 열어 정규화된 RGB 배열로 돌려준다 (탐지·분류의 입력이 됨)."""
    arr = np.array(Image.open(path))
    return normalize_to_uint8_rgb(arr)


def load_scene_for_vis(image_source: Any) -> Optional[np.ndarray]:
    """SAR 이미지를 화면 표시용 RGB 배열로 읽어온다 (밝기 정규화 적용, 실패하면 None)."""
    try:
        arr = np.array(Image.open(image_source))
        return normalize_to_uint8_rgb(arr)
    except Exception:
        return None
