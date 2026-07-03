import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load_dom_rgb(path: str) -> np.ndarray:
    arr = np.array(Image.open(path))
    if arr.dtype != np.uint8:
        values = arr.astype(np.float32)
        positive_values = values[values > 0]
        percentile = np.percentile(positive_values, 99) if positive_values.size else 1.0
        arr = np.clip(values / (percentile + 1e-9) * 255, 0, 255).astype(np.uint8)

    if arr.ndim == 3:
        arr = arr[..., 0]
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)

    return arr
