"""
[EO 도메인 - 이미지 로딩]
EO(일반 컬러 위성/항공 사진) 이미지를 화면 표시용 RGB 배열로 읽어주는 파일.
SAR과 달리 이미 일반 컬러 사진이므로 밝기 정규화를 하지 않는다.
"""
from typing import Any, Optional

import numpy as np
from PIL import Image


def load_image_rgb(image_source: Any) -> Optional[np.ndarray]:
    """EO 이미지를 원본 색 그대로 RGB 배열로 읽어온다 (실패하면 None)."""
    try:
        return np.array(Image.open(image_source).convert("RGB"))
    except Exception:
        return None
