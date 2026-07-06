"""
[SAR 도메인 - 이미지 로딩]
디스크에 저장된 이미지 파일(TIF 등)을 열어, 모델이 바로 쓸 수 있는 형태
(0~255 밝기의 3채널 RGB 배열)로 바꿔 돌려주는 파일.
실제 밝기 정규화 계산은 shared/image_norm.py의 공용 함수를 재사용한다.
"""
import numpy as np
from PIL import Image

from shared.image_norm import normalize_to_uint8_rgb

Image.MAX_IMAGE_PIXELS = None   # 매우 큰 SAR 이미지도 열 수 있도록 픽셀 수 제한을 해제


def load_dom_rgb(path: str) -> np.ndarray:
    """이미지 파일을 열어 정규화된 RGB 배열로 돌려준다 (탐지·분류의 입력이 됨)."""
    arr = np.array(Image.open(path))
    return normalize_to_uint8_rgb(arr)
