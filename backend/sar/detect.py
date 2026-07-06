"""
[SAR 도메인 - 탐지]
이미지 안에서 "차량이 있을 법한 위치(박스)"를 찾아내는 단계.
큰 이미지를 작은 타일로 잘라 YOLO에 넣고, 나온 박스들을 원본 좌표로 되돌린 뒤
너무 크거나 겹치는 박스를 정리해서 돌려준다. (분류는 다음 단계 classify.py가 담당)
"""
from typing import Dict, List

import numpy as np

from backend.sar import config
from backend.sar import models as _m

_BATCH = 16   # YOLO에 한 번에 넣는 타일 개수


def _iou(a, b) -> float:
    """두 박스가 겹치는 정도(0~1)를 계산한다. 1에 가까울수록 거의 같은 위치."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / (union + 1e-9)


def _nms(dets: List[Dict], iou_thr: float = 0.5) -> List[Dict]:
    """같은 물체를 가리키는 중복 박스를 제거한다 (확신도 높은 것만 남김)."""
    dets = sorted(dets, key=lambda d: d["det_conf"], reverse=True)
    keep: List[Dict] = []
    for det in dets:
        if all(_iou(det["bbox"], kept["bbox"]) < iou_thr for kept in keep):
            keep.append(det)
    return keep


def _tile_starts(total: int, tile: int, stride: int) -> List[int]:
    """한 축(가로 또는 세로)을 타일로 자를 때, 각 타일의 시작 좌표 목록을 만든다."""
    if total <= tile:
        return [0]
    starts = list(range(0, total - tile + 1, stride))
    if starts[-1] != total - tile:
        starts.append(total - tile)   # 마지막 자투리 영역도 반드시 포함
    return starts


def detect_on(
    arr_rgb: np.ndarray,
    conf: float = config.DET_CONF,
    smax: int = config.DET_BOX_MAX_PX,
) -> List[Dict]:
    """이미지 한 장을 받아 차량 후보 박스 목록을 돌려준다 (탐지 파이프라인의 본체)."""
    tile = config.DET_TILE_SIZE
    stride = max(1, int(round(tile * (1 - config.DET_OVERLAP))))
    height, width = arr_rgb.shape[:2]

    # 1) 이미지를 격자 모양 타일로 자르고, 각 타일의 원본 위치(offset)를 기억해둔다.
    xs = _tile_starts(width, tile, stride)
    ys = _tile_starts(height, tile, stride)

    tiles, offsets = [], []
    for y0 in ys:
        for x0 in xs:
            tiles.append(arr_rgb[y0:y0 + tile, x0:x0 + tile])
            offsets.append((x0, y0))

    yolo = _m.get_detector_model()
    dets: List[Dict] = []

    # 2) 타일을 묶음(batch) 단위로 YOLO에 넣고, 나온 박스를 원본 좌표로 되돌린다.
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
                # 너무 큰 박스(건물 등)는 여기서 걸러낸다.
                if (bbox[2] - bbox[0]) < smax and (bbox[3] - bbox[1]) < smax:
                    dets.append({"bbox": bbox, "det_conf": float(score)})

    # 3) 타일이 겹친 탓에 생긴 중복 박스를 정리해서 돌려준다.
    return _nms(dets, iou_thr=0.5)
