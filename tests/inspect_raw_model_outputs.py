"""
모델 원본 출력 확인용 진단 스크립트.

FastAPI/Swagger 응답처럼 가공된 JSON이 아니라, 모델 호출 직후의 출력에 가까운 값을
콘솔에 JSON 형태로 찍어본다. 자동 단위 테스트가 아니라 필요할 때 직접 실행하는 도구다.

예시:
  python tests/inspect_raw_model_outputs.py --task eo --image test_52.jpg
  python tests/inspect_raw_model_outputs.py --task sar-yolo --image test_52.jpg --limit 10
  python tests/inspect_raw_model_outputs.py --task sar-cls --image test_52.jpg --box 10,20,80,100
  python tests/inspect_raw_model_outputs.py --task sar-all --image test_52.jpg --limit 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _to_python(value: Any) -> Any:
    """Tensor/ndarray/스칼라를 JSON으로 출력 가능한 기본 타입으로 바꾼다."""
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _print_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=_to_python))


def _parse_box(raw: str) -> List[float]:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--box는 x1,y1,x2,y2 형식이어야 합니다.")
    try:
        return [float(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--box 좌표는 숫자여야 합니다.") from exc


def _topk(prob: torch.Tensor, class_names: List[str], k: int = 5) -> List[Dict[str, Any]]:
    values, indices = torch.topk(prob, k=min(k, prob.numel()))
    return [
        {
            "class_id": int(class_id),
            "label": class_names[int(class_id)] if int(class_id) < len(class_names) else str(int(class_id)),
            "prob": float(score),
        }
        for score, class_id in zip(values, indices)
    ]


def _summarize_yolo_result(result: Any, limit: int) -> Dict[str, Any]:
    """Ultralytics Results 객체에서 대표 원본 필드를 JSON 친화적으로 요약한다."""
    boxes = result.boxes
    box_count = 0 if boxes is None else len(boxes)

    payload: Dict[str, Any] = {
        "result_type": type(result).__name__,
        "path": getattr(result, "path", None),
        "orig_shape": getattr(result, "orig_shape", None),
        "names": getattr(result, "names", None),
        "speed": getattr(result, "speed", None),
        "box_count": box_count,
        "boxes": [],
    }

    if boxes is None or box_count == 0:
        return payload

    take = min(limit, box_count)
    xyxy = boxes.xyxy[:take].detach().cpu().numpy()
    xywh = boxes.xywh[:take].detach().cpu().numpy()
    xyxyn = boxes.xyxyn[:take].detach().cpu().numpy()
    confs = boxes.conf[:take].detach().cpu().numpy()
    classes = boxes.cls[:take].detach().cpu().numpy().astype(int)

    for idx in range(take):
        class_id = int(classes[idx])
        payload["boxes"].append(
            {
                "index": idx,
                "xyxy": xyxy[idx].tolist(),
                "xywh": xywh[idx].tolist(),
                "xyxyn": xyxyn[idx].tolist(),
                "conf": float(confs[idx]),
                "class_id": class_id,
                "label": result.names.get(class_id, str(class_id)),
            }
        )

    try:
        payload["summary"] = result.summary()
    except Exception as exc:
        payload["summary_error"] = str(exc)

    return payload


def inspect_eo(image: Path, limit: int) -> Dict[str, Any]:
    """EO YOLO 모델의 Results 원본 구조를 확인한다."""
    from features.eo.config import DET_CONF, DET_IMGSZ, DET_WEIGHT
    from features.eo.models import get_models_status, get_detector_model, load_models

    ok, err = load_models(DET_WEIGHT)
    if not ok:
        return {"task": "eo", "loaded": False, "error": err}

    model = get_detector_model()
    results = model.predict(
        source=str(image),
        imgsz=DET_IMGSZ,
        conf=DET_CONF,
        device="cpu",
        verbose=False,
    )
    loaded, load_error = get_models_status()
    return {
        "task": "eo",
        "image": str(image),
        "loaded": loaded,
        "load_error": load_error,
        "raw_return_type": type(results).__name__,
        "result_count": len(results),
        "results": [_summarize_yolo_result(result, limit=limit) for result in results],
    }


def _iter_sar_tiles(scene_rgb: np.ndarray, max_tiles: int) -> Iterable[Dict[str, Any]]:
    from features.sar import config
    from features.sar.detect import _tile_starts

    tile = config.DET_TILE_SIZE
    stride = max(1, int(round(tile * (1 - config.DET_OVERLAP))))
    height, width = scene_rgb.shape[:2]
    xs = _tile_starts(width, tile, stride)
    ys = _tile_starts(height, tile, stride)

    count = 0
    for y0 in ys:
        for x0 in xs:
            if max_tiles and count >= max_tiles:
                return
            yield {
                "tile": scene_rgb[y0:y0 + tile, x0:x0 + tile],
                "offset": [x0, y0],
                "tile_index": count,
            }
            count += 1


def inspect_sar_yolo(image: Path, rotate_k: int, limit: int, max_tiles: int) -> Dict[str, Any]:
    """SAR YOLO 탐지기의 타일별 Results 원본 구조를 확인한다."""
    from features.sar import config
    from features.sar.config import CLS_JSON, CLS_WEIGHT, DET_WEIGHT
    from features.sar.image import load_dom_rgb
    from features.sar.models import get_detector_model, get_models_status, load_models
    from features.sar.rotation import rot_k

    ok, err = load_models(DET_WEIGHT, CLS_WEIGHT, CLS_JSON)
    if not ok:
        return {"task": "sar-yolo", "loaded": False, "error": err}

    scene = rot_k(load_dom_rgb(str(image)), rotate_k % 4)
    yolo = get_detector_model()

    tile_summaries = []
    for tile_info in _iter_sar_tiles(scene, max_tiles=max_tiles):
        result = yolo(
            [tile_info["tile"]],
            imgsz=config.DET_TILE_SIZE,
            conf=config.DET_CONF,
            verbose=False,
        )[0]
        summary = _summarize_yolo_result(result, limit=limit)
        summary["tile_index"] = tile_info["tile_index"]
        summary["tile_offset_xy"] = tile_info["offset"]
        tile_summaries.append(summary)

    loaded, load_error = get_models_status()
    return {
        "task": "sar-yolo",
        "image": str(image),
        "rotate_k": rotate_k % 4,
        "loaded": loaded,
        "load_error": load_error,
        "note": "boxes 좌표는 타일 기준입니다. tile_offset_xy를 더하면 회전된 전체 이미지 기준 좌표가 됩니다.",
        "tile_count_returned": len(tile_summaries),
        "tiles": tile_summaries,
    }


def inspect_sar_cls(image: Path, boxes: Optional[List[List[float]]], limit: int) -> Dict[str, Any]:
    """SAR ConvNeXt 분류기의 logits/probs 원본 텐서를 확인한다."""
    from features.sar.classify import _cls_transform, _extract_chip
    from features.sar.config import CLS_JSON, CLS_WEIGHT, DET_WEIGHT
    from features.sar.detect import detect_on
    from features.sar.image import load_dom_rgb
    from features.sar.models import get_class_names, get_classifier, load_models

    ok, err = load_models(DET_WEIGHT, CLS_WEIGHT, CLS_JSON)
    if not ok:
        return {"task": "sar-cls", "loaded": False, "error": err}

    scene = load_dom_rgb(str(image))
    selected_boxes = boxes
    if not selected_boxes:
        selected_boxes = [item["bbox"] for item in detect_on(scene)[:limit]]

    if not selected_boxes:
        return {
            "task": "sar-cls",
            "image": str(image),
            "loaded": True,
            "boxes": [],
            "message": "분류할 박스가 없습니다. --box x1,y1,x2,y2 를 직접 지정해보세요.",
        }

    chips = [_cls_transform(_extract_chip(scene, box)) for box in selected_boxes]
    batch = torch.stack(chips)
    with torch.no_grad():
        logits = get_classifier()(batch)
        probs = torch.softmax(logits, dim=1)

    class_names = get_class_names()
    rows = []
    for idx, (box, logit, prob) in enumerate(zip(selected_boxes, logits, probs)):
        pred_id = int(prob.argmax())
        rows.append(
            {
                "index": idx,
                "bbox": box,
                "raw_logits": logit.detach().cpu().tolist(),
                "softmax_probs": prob.detach().cpu().tolist(),
                "pred_class_id": pred_id,
                "pred_label": class_names[pred_id],
                "pred_prob": float(prob.max()),
                "top5": _topk(prob, class_names, k=5),
            }
        )

    return {
        "task": "sar-cls",
        "image": str(image),
        "loaded": True,
        "class_names": class_names,
        "logits_shape": list(logits.shape),
        "items": rows,
    }


def inspect_sar_all(image: Path, rotate_k: int, limit: int) -> Dict[str, Any]:
    """현재 SAR 파이프라인 최종 결과와 ConvNeXt 원본 logits/probs를 함께 확인한다."""
    from features.sar.classify import _cls_transform, _extract_chip
    from features.sar.config import CLS_JSON, CLS_WEIGHT, DET_WEIGHT
    from features.sar.detect import detect_on
    from features.sar.image import load_dom_rgb
    from features.sar.models import get_class_names, get_classifier, load_models
    from features.sar.rotation import inv_box, rot_k

    ok, err = load_models(DET_WEIGHT, CLS_WEIGHT, CLS_JSON)
    if not ok:
        return {"task": "sar-all", "loaded": False, "error": err}

    scene = load_dom_rgb(str(image))
    height, width = scene.shape[:2]
    chosen_k = rotate_k % 4
    rotated = rot_k(scene, chosen_k)
    detections_rotated = detect_on(rotated)[:limit]

    rotated_boxes = [item["bbox"] for item in detections_rotated]
    original_boxes = [inv_box(box, width, height, chosen_k) for box in rotated_boxes]

    class_names = get_class_names()
    cls_rows = []
    if rotated_boxes:
        chips = [_cls_transform(_extract_chip(rotated, box)) for box in rotated_boxes]
        batch = torch.stack(chips)
        with torch.no_grad():
            logits = get_classifier()(batch)
            probs = torch.softmax(logits, dim=1)

        for idx, (det, original_box, logit, prob) in enumerate(
            zip(detections_rotated, original_boxes, logits, probs)
        ):
            pred_id = int(prob.argmax())
            cls_rows.append(
                {
                    "index": idx,
                    "rotated_bbox": det["bbox"],
                    "original_bbox": original_box,
                    "det_conf": det["det_conf"],
                    "raw_logits": logit.detach().cpu().tolist(),
                    "softmax_probs": prob.detach().cpu().tolist(),
                    "pred_class_id": pred_id,
                    "pred_label": class_names[pred_id],
                    "pred_prob": float(prob.max()),
                    "top5": _topk(prob, class_names, k=5),
                }
            )

    final_detections = [
        {
            "bbox": item["original_bbox"],
            "label": item["pred_label"],
            "det_conf": item["det_conf"],
            "cls_conf": item["pred_prob"],
        }
        for item in cls_rows
    ]

    return {
        "task": "sar-all",
        "image": str(image),
        "rotate_k": chosen_k,
        "loaded": True,
        "pipeline_final_detections": final_detections,
        "classifier_raw_for_rotated_boxes": cls_rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EO/SAR 모델 원본 출력 확인 도구")
    parser.add_argument("--task", choices=["eo", "sar-yolo", "sar-cls", "sar-all"], required=True)
    parser.add_argument("--image", type=Path, required=True, help="입력 이미지 경로")
    parser.add_argument("--limit", type=int, default=5, help="출력할 박스/항목 최대 개수")
    parser.add_argument("--rotate-k", type=int, default=0, help="SAR 회전값: 0, 1, 2, 3")
    parser.add_argument(
        "--max-tiles",
        type=int,
        default=20,
        help="sar-yolo에서 확인할 타일 수. 0이면 전체 타일을 확인한다.",
    )
    parser.add_argument(
        "--box",
        action="append",
        type=_parse_box,
        help="sar-cls용 박스 좌표. 예: --box 10,20,80,100. 여러 번 지정 가능.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    image = args.image.resolve()
    if not image.exists():
        raise SystemExit(f"이미지 파일을 찾을 수 없습니다: {image}")

    if args.task == "eo":
        payload = inspect_eo(image, limit=args.limit)
    elif args.task == "sar-yolo":
        payload = inspect_sar_yolo(
            image,
            rotate_k=args.rotate_k,
            limit=args.limit,
            max_tiles=args.max_tiles,
        )
    elif args.task == "sar-cls":
        payload = inspect_sar_cls(image, boxes=args.box, limit=args.limit)
    else:
        payload = inspect_sar_all(image, rotate_k=args.rotate_k, limit=args.limit)

    _print_json(payload)


if __name__ == "__main__":
    main()
