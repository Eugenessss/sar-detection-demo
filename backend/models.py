import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import torch
import torch.nn as nn
from torchvision.models import convnext_tiny

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

torch.set_num_threads(os.cpu_count() or 4)

# ── 지연 로드 전역 객체 ──────────────────────────────────────────
_det_model = None
_det_sahi = None
_classifier = None
_class_names: List[str] = []
_type2group: Dict[str, str] = {}
_models_loaded = False
_load_error: Optional[str] = None


def get_models_status() -> Tuple[bool, Optional[str]]:
    return _models_loaded, _load_error


def load_models(det_weight, cls_weight, cls_json) -> Tuple[bool, Optional[str]]:
    """앱 시작 시 1회 호출. 성공하면 True, 실패하면 (False, 오류메시지)."""
    global _det_model, _det_sahi, _classifier, _class_names, _type2group
    global _models_loaded, _load_error

    missing = []
    for p, label in [(det_weight, "탐지 가중치"), (cls_weight, "분류 가중치"), (cls_json, "클래스 JSON")]:
        if not Path(p).exists():
            missing.append(f"{label}: {p}")

    if missing:
        _load_error = "필요한 파일이 없습니다:\n" + "\n".join(missing)
        log.error(_load_error)
        return False, _load_error

    try:
        # ── 탐지기 (ultralytics YOLO 직접 로드 — 수동 타일링/배치용) ──
        from ultralytics import YOLO
        _det_model = YOLO(str(det_weight))

        # ── 탐지기 (SAHI 래퍼 — 비교용) ──
        from sahi import AutoDetectionModel
        _det_sahi = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=str(det_weight),
            confidence_threshold=0.3,
            device="cpu",
            image_size=256,
        )

        # ── 클래스 정보 ────────────────────────────────────────────
        with open(cls_json, encoding="utf-8") as f:
            j = json.load(f)
        _class_names = j["classes"]
        _type2group  = j.get("type2group", {})
        num_cls = len(_class_names)

        # ── 분류기 (ConvNeXt-Tiny) ─────────────────────────────────
        _classifier = convnext_tiny()
        _classifier.classifier[2] = nn.Linear(
            _classifier.classifier[2].in_features, num_cls
        )
        _classifier.load_state_dict(torch.load(str(cls_weight), map_location="cpu"))
        _classifier = _classifier.eval()

        _models_loaded = True
        _load_error = None
        log.info("모델 로드 완료. 클래스 수=%d", num_cls)
        return True, None

    except Exception as e:
        _load_error = f"모델 로드 실패: {e}"
        log.exception(_load_error)
        return False, _load_error
