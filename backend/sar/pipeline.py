from typing import Dict, List

import numpy as np

from backend.sar.classify import classify_boxes_batch
from backend.sar.detect import detect_on
from backend.sar.rotation import _verify_inv_box, inv_box, rot_k


def run_full_inference(
    scene_rgb: np.ndarray,
    k: int,
    detect_fn=detect_on,
) -> List[Dict]:
    """Run detection and classification, then map boxes to original coordinates."""
    height, width = scene_rgb.shape[:2]
    _verify_inv_box(width, height)

    rotated = rot_k(scene_rgb, k)
    detections_rotated = detect_fn(rotated)
    boxes_original = [inv_box(item["bbox"], width, height, k) for item in detections_rotated]

    labels_confs = classify_boxes_batch(rotated, [item["bbox"] for item in detections_rotated])

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
