"""
핵심 파이프라인 로직 — 노트북 pipeline/soc14/dom48_convnext_yolo11n.ipynb 이식.
값(conf, tile, overlap, crop 크기, transform) 은 노트북과 동일하게 유지.
"""
import logging
from typing import List, Tuple, Optional, Dict

import numpy as np

from backend.detect import detect_on
from backend.classify import classify_boxes_batch
from backend.rotation import rot_k, inv_box, _verify_inv_box
from backend.gt import iou

log = logging.getLogger(__name__)

# ── 탐지 캐시 타입 별칭 ────────────────────────────────────────────
# (det_rot, det_orig): 회전본 박스 목록과 원본 좌표 변환 목록
_DetCache = Tuple[List[Dict], List[List[float]]]


# ══════════════════════════════════════════════════════════════════
# 6) 회전 최적화 (eval_at_k + correct_rotation)
# ══════════════════════════════════════════════════════════════════
def eval_at_k(
    scene_rgb: np.ndarray,
    gt: List[Tuple[List[float], str]],
    k: int,
    cached_det: Optional[_DetCache] = None,
    detect_fn=detect_on,
) -> Tuple[float, float, int, _DetCache]:
    """
    k 회전 후 탐지→GT매칭→분류 평가.
    cached_det 가 주어지면 탐지를 건너뛰고 재사용.
    반환: (recall, cls_on_det, n_det, (det_rot, det_orig))
    """
    H0, W0 = scene_rgb.shape[:2]
    rot = rot_k(scene_rgb, k)

    if cached_det is not None:
        det_rot, det_orig = cached_det
    else:
        det_rot = detect_fn(rot)
        det_orig = [inv_box(d["bbox"], W0, H0, k) for d in det_rot]

    # GT 매칭 — 노트북 원본 로직 유지
    matches: List[Tuple[int, str]] = []
    for gbox, gtype in gt:
        bi, biou = -1, 0.3
        for i, dob in enumerate(det_orig):
            v = iou(gbox, dob)
            if v >= biou:
                biou, bi = v, i
        matches.append((bi, gtype))

    # GT에 매칭된 고유 det 인덱스만 배치 분류
    unique_bis = list(dict.fromkeys(bi for bi, _ in matches if bi >= 0))
    if unique_bis:
        batch_results = classify_boxes_batch(rot, [det_rot[bi]["bbox"] for bi in unique_bis])
        bi_label = {bi: lbl for bi, (lbl, _) in zip(unique_bis, batch_results)}
    else:
        bi_label = {}

    n_det = n_cls = 0
    for bi, gtype in matches:
        if bi >= 0:
            n_det += 1
            if bi_label.get(bi) == gtype:
                n_cls += 1

    N = max(len(gt), 1)
    recall = n_det / N
    cls_on_det = n_cls / n_det if n_det else 0.0
    return recall, cls_on_det, len(det_orig), (det_rot, det_orig)


def correct_rotation(
    scene_rgb: np.ndarray,
    gt: List[Tuple[List[float], str]],
    azi: int,
    detect_fn=detect_on,
) -> Tuple[int, float, float, int, _DetCache]:
    """
    최근접 90° 스냅 + 180° 모호성 E2E 최대로 결정.
    반환: (k, recall, cls_on_det, n_det, winner_det_cache)
    winner_det_cache 를 run_full_inference 에 넘기면 재탐지를 생략한다.
    """
    base_k = int(round(azi / 90.0)) % 4
    best = None
    cache_by_k: Dict[int, _DetCache] = {}

    for k in [base_k]:   # 180° 모호성 검사 생략 → 탐지 1회 (방위각 신뢰)
        r, c, nb, det_cache = eval_at_k(scene_rgb, gt, k, detect_fn=detect_fn)
        cache_by_k[k] = det_cache
        score = r * c
        if best is None or score > best[0]:
            best = (score, k, r, c, nb)

    _, k, r, c, nb = best
    return k, r, c, nb, cache_by_k[k]


# ══════════════════════════════════════════════════════════════════
# 7) 최종 추론 — 결정된 k로 탐지+분류+GT채점
# ══════════════════════════════════════════════════════════════════
def run_full_inference(
    scene_rgb: np.ndarray,
    k: int,
    gt: Optional[List[Tuple[List[float], str]]] = None,
    cached_det: Optional[_DetCache] = None,
    detect_fn=detect_on,
) -> Tuple[List[Dict], Optional[Dict], List[Dict]]:
    """
    k 회전본에서 탐지+분류 후 inv_box로 원좌표 변환.
    cached_det 가 주어지면 탐지를 건너뛰고 재사용 (correct_rotation 캐시 활용).
    GT 있으면 매칭 및 status 채점.
    반환: (detections, metrics_or_None)
    """
    H0, W0 = scene_rgb.shape[:2]
    _verify_inv_box(W0, H0)

    rot = rot_k(scene_rgb, k)

    if cached_det is not None:
        det_rot, det_orig = cached_det
    else:
        det_rot = detect_fn(rot)
        det_orig = [inv_box(d["bbox"], W0, H0, k) for d in det_rot]

    # 전체 박스 배치 분류 (1회 forward pass)
    labels_confs = classify_boxes_batch(rot, [d["bbox"] for d in det_rot])

    detections = [
        {
            "bbox":     orig_box,
            "det_conf": d["det_conf"],
            "label":    label,
            "cls_conf": cls_conf,
            "status":   "fp",
        }
        for d, (label, cls_conf), orig_box in zip(det_rot, labels_confs, det_orig)
    ]

    metrics = None
    missed: List[Dict] = []
    if gt:
        n_matched = n_correct = 0
        matched_det_idx = set()

        for gbox, gtype in gt:
            bi, biou = -1, 0.3
            for i, det in enumerate(detections):
                v = iou(gbox, det["bbox"])
                if v >= biou:
                    biou, bi = v, i
            if bi >= 0 and bi not in matched_det_idx:
                matched_det_idx.add(bi)
                n_matched += 1
                detections[bi]["status"] = "correct" if detections[bi]["label"] == gtype else "wrong"
                if detections[bi]["label"] == gtype:
                    n_correct += 1
            else:
                # 미탐지(False Negative): 탐지와 매칭되지 않은 GT 객체
                missed.append({
                    "bbox":     [float(v) for v in gbox],
                    "label":    gtype,
                    "status":   "missed",
                    "det_conf": None,
                    "cls_conf": None,
                })

        n_gt = len(gt)
        recall     = n_matched / max(n_gt, 1)
        cls_on_det = n_correct / max(n_matched, 1)
        e2e        = recall * cls_on_det
        metrics = {
            "n_gt":       n_gt,
            "n_matched":  n_matched,
            "n_missed":   len(missed),
            "recall":     round(recall, 4),
            "cls_on_det": round(cls_on_det, 4),
            "E2E":        round(e2e, 4),
        }

    return detections, metrics, missed
