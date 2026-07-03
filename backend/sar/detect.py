from typing import Dict, List

import numpy as np

from backend.sar import config
from backend.sar import models as _m

_BATCH = 16


def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / (union + 1e-9)


def _nms(dets: List[Dict], iou_thr: float = 0.5) -> List[Dict]:
    """Remove duplicate boxes with greedy NMS."""
    dets = sorted(dets, key=lambda d: d["det_conf"], reverse=True)
    keep: List[Dict] = []
    for det in dets:
        if all(_iou(det["bbox"], kept["bbox"]) < iou_thr for kept in keep):
            keep.append(det)
    return keep


def _tile_starts(total: int, tile: int, stride: int) -> List[int]:
    if total <= tile:
        return [0]
    starts = list(range(0, total - tile + 1, stride))
    if starts[-1] != total - tile:
        starts.append(total - tile)
    return starts


def detect_on(
    arr_rgb: np.ndarray,
    conf: float = config.DET_CONF,
    smax: int = config.DET_BOX_MAX_PX,
) -> List[Dict]:
    tile = config.DET_TILE_SIZE
    stride = max(1, int(round(tile * (1 - config.DET_OVERLAP))))
    height, width = arr_rgb.shape[:2]

    xs = _tile_starts(width, tile, stride)
    ys = _tile_starts(height, tile, stride)

    tiles, offsets = [], []
    for y0 in ys:
        for x0 in xs:
            tiles.append(arr_rgb[y0:y0 + tile, x0:x0 + tile])
            offsets.append((x0, y0))

    yolo = _m.get_detector_model()
    dets: List[Dict] = []

    for i in range(0, len(tiles), _BATCH):
        batch = tiles[i:i + _BATCH]
        batch_offsets = offsets[i:i + _BATCH]
        results = yolo(batch, imgsz=tile, conf=conf, verbose=False)
        for result, (x0, y0) in zip(results, batch_offsets):
            if result.boxes is None or len(result.boxes) == 0:
                continue
            xyxy = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            for (bx1, by1, bx2, by2), score in zip(xyxy, confs):
                bbox = [float(bx1 + x0), float(by1 + y0), float(bx2 + x0), float(by2 + y0)]
                if (bbox[2] - bbox[0]) < smax and (bbox[3] - bbox[1]) < smax:
                    dets.append({"bbox": bbox, "det_conf": float(score)})

    return _nms(dets, iou_thr=0.5)
