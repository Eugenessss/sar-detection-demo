import re
import logging
from typing import List, Tuple, Optional

import numpy as np

log = logging.getLogger(__name__)


def rot_k(arr: np.ndarray, k: int) -> np.ndarray:
    return np.rot90(arr, k)


def _fwd_pt(x: float, y: float, W: int, H: int, k: int) -> Tuple[float, float]:
    for _ in range(k % 4):
        x, y = y, (W - 1) - x
        W, H = H, W
    return x, y


def _dims_after(W: int, H: int, k: int) -> Tuple[int, int]:
    return (H, W) if k % 2 else (W, H)


def inv_box(box: List[float], W: int, H: int, k: int) -> List[float]:
    """회전본 좌표 → 원본 좌표 역변환."""
    Wt, Ht = _dims_after(W, H, k)
    kk = (4 - k % 4) % 4
    pts = [
        (box[0], box[1]),
        (box[2], box[1]),
        (box[2], box[3]),
        (box[0], box[3]),
    ]
    xs, ys = zip(*[_fwd_pt(px, py, Wt, Ht, kk) for px, py in pts])
    return [min(xs), min(ys), max(xs), max(ys)]


def _verify_inv_box(W: int, H: int) -> None:
    """inv_box 자기검증 — 정변환 후 역변환이 원좌표를 복원하는지 assert."""
    test_box = [10.0, 20.0, 50.0, 60.0]
    for k in range(4):
        # forward: 원본 → 회전본
        Wt, Ht = _dims_after(W, H, k)
        fwd_pts = [(p[0], p[1]) for p in [
            (test_box[0], test_box[1]),
            (test_box[2], test_box[1]),
            (test_box[2], test_box[3]),
            (test_box[0], test_box[3]),
        ]]
        fxs, fys = zip(*[_fwd_pt(px, py, W, H, k) for px, py in fwd_pts])
        rot_box = [min(fxs), min(fys), max(fxs), max(fys)]
        # inverse
        recovered = inv_box(rot_box, W, H, k)
        for orig, rec in zip(test_box, recovered):
            assert abs(orig - rec) < 1.0, (
                f"inv_box 자기검증 실패: k={k}, orig={test_box}, recovered={recovered}"
            )
    log.debug("inv_box 자기검증 통과 (W=%d, H=%d)", W, H)


def parse_azi(path: str) -> Optional[int]:
    """폴더/파일명에서 방위각 추출 (예: 120azi)."""
    m = re.search(r"(\d+)azi", path)
    return int(m.group(1)) if m else None
