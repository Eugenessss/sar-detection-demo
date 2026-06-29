import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load_dom_rgb(path: str) -> np.ndarray:
    arr = np.array(Image.open(path))
    if arr.dtype != np.uint8:                        # 16bit 등 → 99퍼센타일 정규화
        a = arr.astype(np.float32)
        p = np.percentile(a[a > 0], 99)
        arr = np.clip(a / (p + 1e-9) * 255, 0, 255).astype(np.uint8)
    if arr.ndim == 3:
        arr = arr[..., 0]                            # 다채널이면 1채널만
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)           # 1채널 → 3채널
    return arr
