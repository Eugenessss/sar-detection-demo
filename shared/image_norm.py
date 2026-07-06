"""
[공용 - 이미지 정규화]
백엔드(추론용)와 프론트엔드(화면 표시용) 양쪽에서 똑같이 필요한 '밝기 정규화' 계산을
한곳에 모아둔 파일. SAR 원본은 밝기 범위가 제각각이라, 이를 0~255로 맞추고 흑백을
3채널로 펼쳐줘야 모델과 화면이 다룰 수 있다. (무거운 ML 라이브러리에 의존하지 않는 순수 계산)
"""
import numpy as np


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
