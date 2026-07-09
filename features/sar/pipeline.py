"""
[SAR 도메인 - 파이프라인]
"이미지 회전 → 탐지 → 분류 → 좌표 되돌리기"라는 전체 추론 순서를 하나로 엮는 파일.
detect.py / classify.py / rotation.py를 순서대로 호출해 최종 결과 목록을 만든다.
이 파일이 SAR 도메인 로직의 '조립 지점'이며, api.py의 추론 use case가 이 함수를 호출한다.
"""
from typing import Dict, List

import numpy as np

from features.sar.classify import classify_boxes_batch
from features.sar.detect import detect_on
from features.sar.rotation import _verify_inv_box, inv_box, rot_k


def run_full_inference(
    scene_rgb: np.ndarray,
    k: int,
    detect_fn=detect_on,
) -> List[Dict]:
    """이미지 한 장에 대해 탐지+분류를 수행하고, 박스를 원본 좌표로 맞춘 결과를 돌려준다."""
    height, width = scene_rgb.shape[:2]
    _verify_inv_box(width, height)   # 좌표 변환이 정상인지 먼저 자가 점검

    # 1) 이미지를 k번 회전시켜 탐지에 넣는다.
    rotated = rot_k(scene_rgb, k)
    detections_rotated = detect_fn(rotated)

    # 2) 탐지된 박스를 원본 이미지 기준 좌표로 되돌린다.
    boxes_original = [inv_box(item["bbox"], width, height, k) for item in detections_rotated]

    # 3) (회전된 이미지 위에서) 각 박스가 어떤 차량인지 분류한다.
    labels_confs = classify_boxes_batch(rotated, [item["bbox"] for item in detections_rotated])

    # 4) 위치·탐지확신도·분류결과를 하나로 합쳐 최종 목록을 만든다.
    return [
        {
            "bbox": original_box,
            "det_conf": item["det_conf"],
            "label": label,
            "cls_conf": cls_conf,
        }
        for item, (label, cls_conf), original_box in zip(
            detections_rotated,
            labels_confs,
            boxes_original,
        )
    ]
