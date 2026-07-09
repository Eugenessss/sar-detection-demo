"""
[SAR 도메인 - 회전/좌표 변환]
SAR 이미지는 촬영 방위각에 따라 차량이 눕거나 기울어 보인다. 그래서 탐지 전에 이미지를
90도 단위로 돌려서 넣는데, 돌린 이미지에서 찾은 박스는 좌표계가 바뀌어 있으므로
다시 원본 이미지 기준 좌표로 되돌려줘야 한다. 그 회전과 역변환 계산을 담당하는 파일.
"""
import logging
import re
from typing import List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


def rot_k(arr: np.ndarray, k: int) -> np.ndarray:
    """이미지를 반시계 방향으로 90도씩 k번 돌린다 (k=0,1,2,3 → 0,90,180,270도)."""
    return np.rot90(arr, k)


def _fwd_pt(x: float, y: float, width: int, height: int, k: int) -> Tuple[float, float]:
    """한 점(x, y)이 이미지를 k번 회전했을 때 어느 위치로 가는지 계산한다."""
    for _ in range(k % 4):
        x, y = y, (width - 1) - x
        width, height = height, width
    return x, y


def _dims_after(width: int, height: int, k: int) -> Tuple[int, int]:
    """이미지를 k번 회전한 뒤의 (가로, 세로) 크기를 돌려준다 (홀수 회전은 가로·세로가 바뀜)."""
    return (height, width) if k % 2 else (width, height)


def inv_box(box: List[float], width: int, height: int, k: int) -> List[float]:
    """회전된 이미지에서 찾은 박스를, 원래 이미지 기준 좌표로 되돌린다."""
    rotated_width, rotated_height = _dims_after(width, height, k)
    inverse_k = (4 - k % 4) % 4   # 원래대로 되돌리려면 반대 방향으로 회전
    # 박스의 네 꼭짓점을 각각 되돌린 뒤, 그것들을 감싸는 새 박스를 만든다.
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
    """좌표 변환이 제대로 되는지 실행 중에 스스로 점검하는 안전장치 (틀리면 즉시 에러)."""
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
    """파일 이름에서 방위각을 뽑아낸다 (예: 'DOM_120azi_sample.tif' → 120). 없으면 None."""
    match = re.search(r"(\d+)azi", path, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None
