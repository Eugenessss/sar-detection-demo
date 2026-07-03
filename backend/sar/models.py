import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
from torchvision.models import convnext_tiny

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

torch.set_num_threads(os.cpu_count() or 4)

_det_model = None
_classifier = None
_class_names: List[str] = []
_type2group: Dict[str, str] = {}
_models_loaded = False
_load_error: Optional[str] = None


def get_models_status() -> Tuple[bool, Optional[str]]:
    return _models_loaded, _load_error


def get_detector_model():
    return _det_model


def get_classifier():
    return _classifier


def get_class_names() -> List[str]:
    return _class_names


def map_type_to_group(type_name: str) -> str:
    return _type2group.get(type_name, type_name)


def load_models(det_weight, cls_weight, cls_json) -> Tuple[bool, Optional[str]]:
    """Load detector, classifier, and class metadata once during app startup."""
    global _det_model, _classifier, _class_names, _type2group
    global _models_loaded, _load_error

    missing = []
    for path, label in [
        (det_weight, "탐지 가중치"),
        (cls_weight, "분류 가중치"),
        (cls_json, "클래스 JSON"),
    ]:
        if not Path(path).exists():
            missing.append(f"{label}: {path}")

    if missing:
        _models_loaded = False
        _load_error = "필요한 파일이 없습니다:\n" + "\n".join(missing)
        log.error(_load_error)
        return False, _load_error

    try:
        from ultralytics import YOLO

        _det_model = YOLO(str(det_weight))

        with open(cls_json, encoding="utf-8") as f:
            metadata = json.load(f)
        _class_names = metadata["classes"]
        _type2group = metadata.get("type2group", {})
        num_classes = len(_class_names)

        _classifier = convnext_tiny()
        _classifier.classifier[2] = nn.Linear(
            _classifier.classifier[2].in_features,
            num_classes,
        )
        _classifier.load_state_dict(torch.load(str(cls_weight), map_location="cpu"))
        _classifier = _classifier.eval()

        _models_loaded = True
        _load_error = None
        log.info("모델 로드 완료. 클래스 수: %d", num_classes)
        return True, None

    except Exception as exc:
        _models_loaded = False
        _load_error = f"모델 로드 실패: {exc}"
        log.exception(_load_error)
        return False, _load_error
