"""
탐지 — 수동 타일링 + 배치 추론 (SAHI 미사용).
값(타일 256, overlap 0.25, conf 0.3, <100px)은 노트북과 동일하게 유지.
"""
from typing import List, Dict

import numpy as np

from backend import config
from backend import models as _m

_BATCH = 16   # 타일 미니배치 크기


def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / (ua + 1e-9)


def _nms(dets: List[Dict], iou_thr: float = 0.5) -> List[Dict]:
    """타일 overlap에서 생기는 중복 박스 제거 (confidence 우선 greedy NMS)."""
    dets = sorted(dets, key=lambda d: d["det_conf"], reverse=True)
    keep: List[Dict] = []
    for d in dets:
        if all(_iou(d["bbox"], k["bbox"]) < iou_thr for k in keep):
            keep.append(d)
    return keep


def _tile_starts(total: int, tile: int, stride: int) -> List[int]:
    if total <= tile:
        return [0]
    xs = list(range(0, total - tile + 1, stride))
    if xs[-1] != total - tile:        # 마지막 타일은 경계에 딱 맞춤
        xs.append(total - tile)
    return xs


def detect_on(arr_rgb: np.ndarray,
              conf: float = config.DET_CONF,
              smax: int = config.DET_BOX_MAX_PX) -> List[Dict]:
    tile   = config.DET_TILE_SIZE
    stride = max(1, int(round(tile * (1 - config.DET_OVERLAP))))
    H, W = arr_rgb.shape[:2]

    xs = _tile_starts(W, tile, stride)
    ys = _tile_starts(H, tile, stride)

    tiles, offsets = [], []
    for y0 in ys:
        for x0 in xs:
            tiles.append(arr_rgb[y0:y0 + tile, x0:x0 + tile])
            offsets.append((x0, y0))

    yolo = _m._det_model
    dets: List[Dict] = []

    for i in range(0, len(tiles), _BATCH):
        batch = tiles[i:i + _BATCH]
        offs  = offsets[i:i + _BATCH]
        results = yolo(batch, imgsz=tile, conf=conf, verbose=False)
        for res, (x0, y0) in zip(results, offs):
            if res.boxes is None or len(res.boxes) == 0:
                continue
            xyxy = res.boxes.xyxy.cpu().numpy()
            cfs  = res.boxes.conf.cpu().numpy()
            for (bx1, by1, bx2, by2), c in zip(xyxy, cfs):
                gb = [float(bx1 + x0), float(by1 + y0), float(bx2 + x0), float(by2 + y0)]
                if (gb[2] - gb[0]) < smax and (gb[3] - gb[1]) < smax:
                    dets.append({"bbox": gb, "det_conf": float(c)})

    return _nms(dets, iou_thr=0.5)


def detect_on_sahi(arr_rgb: np.ndarray,
                   conf: float = config.DET_CONF,
                   smax: int = config.DET_BOX_MAX_PX) -> List[Dict]:
    """비교용 — 원래의 SAHI 슬라이스 추론 (노트북 방식)."""
    from sahi.predict import get_sliced_prediction
    _m._det_sahi.confidence_threshold = conf
    r = get_sliced_prediction(
        arr_rgb, _m._det_sahi,
        slice_height=config.DET_TILE_SIZE, slice_width=config.DET_TILE_SIZE,
        overlap_height_ratio=config.DET_OVERLAP, overlap_width_ratio=config.DET_OVERLAP,
        perform_standard_pred=False, verbose=0,
    )
    out = []
    for p in r.object_prediction_list:
        b = [p.bbox.minx, p.bbox.miny, p.bbox.maxx, p.bbox.maxy]
        if (b[2] - b[0]) < smax and (b[3] - b[1]) < smax:
            out.append({"bbox": b, "det_conf": float(p.score.value)})
    return out
