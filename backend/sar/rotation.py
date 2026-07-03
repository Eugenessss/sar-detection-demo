import logging
import re
from typing import List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


def rot_k(arr: np.ndarray, k: int) -> np.ndarray:
    return np.rot90(arr, k)


def _fwd_pt(x: float, y: float, width: int, height: int, k: int) -> Tuple[float, float]:
    for _ in range(k % 4):
        x, y = y, (width - 1) - x
        width, height = height, width
    return x, y


def _dims_after(width: int, height: int, k: int) -> Tuple[int, int]:
    return (height, width) if k % 2 else (width, height)


def inv_box(box: List[float], width: int, height: int, k: int) -> List[float]:
    """Map a box from rotated image coordinates back to original coordinates."""
    rotated_width, rotated_height = _dims_after(width, height, k)
    inverse_k = (4 - k % 4) % 4
    points = [
        (box[0], box[1]),
        (box[2], box[1]),
        (box[2], box[3]),
        (box[0], box[3]),
    ]
    xs, ys = zip(
        *[
            _fwd_pt(px, py, rotated_width, rotated_height, inverse_k)
            for px, py in points
        ]
    )
    return [min(xs), min(ys), max(xs), max(ys)]


def _verify_inv_box(width: int, height: int) -> None:
    """Lightweight runtime guard for coordinate round trips."""
    test_box = [10.0, 20.0, 50.0, 60.0]
    for k in range(4):
        points = [
            (test_box[0], test_box[1]),
            (test_box[2], test_box[1]),
            (test_box[2], test_box[3]),
            (test_box[0], test_box[3]),
        ]
        fxs, fys = zip(*[_fwd_pt(px, py, width, height, k) for px, py in points])
        rotated_box = [min(fxs), min(fys), max(fxs), max(fys)]
        recovered = inv_box(rotated_box, width, height, k)
        for original, actual in zip(test_box, recovered):
            assert abs(original - actual) < 1.0, (
                f"inv_box self-check failed: k={k}, "
                f"original={test_box}, recovered={recovered}"
            )
    log.debug("inv_box self-check passed (width=%d, height=%d)", width, height)


def parse_azi(path: str) -> Optional[int]:
    """Extract azimuth from names such as DOM_120azi_sample.tif."""
    match = re.search(r"(\d+)azi", path, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None
