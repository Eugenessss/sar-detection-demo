"""
[테스트 - 회전/좌표 변환]
backend/sar/rotation.py의 좌표 계산이 정확한지 검증하는 단위 테스트.
버그가 나기 쉬운 순수 수학 로직이라 우선적으로 테스트를 붙여둔다.
'python -m unittest discover tests'로 실행한다.
"""
import unittest

import numpy as np

from backend.sar.rotation import inv_box, parse_azi, rot_k


def _dims_after(width: int, height: int, k: int) -> tuple[int, int]:
    return (height, width) if k % 2 else (width, height)


def _forward_point(x: float, y: float, width: int, height: int, k: int) -> tuple[float, float]:
    for _ in range(k % 4):
        x, y = y, (width - 1) - x
        width, height = height, width
    return x, y


def _forward_box(box: list[float], width: int, height: int, k: int) -> list[float]:
    points = [
        (box[0], box[1]),
        (box[2], box[1]),
        (box[2], box[3]),
        (box[0], box[3]),
    ]
    xs, ys = zip(*[_forward_point(x, y, width, height, k) for x, y in points])
    return [min(xs), min(ys), max(xs), max(ys)]


class RotationTest(unittest.TestCase):
    def test_parse_azi_from_filename(self):
        self.assertEqual(parse_azi("DOM_120azi_sample.tif"), 120)
        self.assertIsNone(parse_azi("DOM_sample_without_angle.tif"))

    def test_rot_k_swaps_dimensions_for_odd_rotations(self):
        image = np.zeros((20, 30, 3), dtype=np.uint8)

        for k in range(4):
            rotated = rot_k(image, k)
            expected_width, expected_height = _dims_after(30, 20, k)
            self.assertEqual(rotated.shape[:2], (expected_height, expected_width))

    def test_inv_box_round_trips_forward_box(self):
        width, height = 200, 120
        original = [10.0, 20.0, 50.0, 60.0]

        for k in range(4):
            with self.subTest(k=k):
                rotated_box = _forward_box(original, width, height, k)
                recovered = inv_box(rotated_box, width, height, k)
                for expected, actual in zip(original, recovered):
                    self.assertAlmostEqual(expected, actual, delta=1.0)


if __name__ == "__main__":
    unittest.main()
