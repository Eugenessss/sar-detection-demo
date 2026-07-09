"""
[SAR 도메인 - 모델 보관소]
탐지기/분류기 모델과 클래스 이름을 딱 한 번 메모리에 올려두고
이후 추론마다 꺼내 쓰도록 보관하는 파일. (모듈 전역 변수에 담아 캐시 역할)
- load_models(): 첫 사용 시 loader.py가 한 번 호출해 모델을 메모리에 적재한다.
- get_*(): 적재된 모델/클래스 이름을 꺼내오는 창구.
"""
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

# 아래 전역 변수들이 "한 번 로드해서 계속 재사용"하는 실제 저장 공간이다.
_det_model = None                      # 탐지기(YOLO) 모델
_classifier = None                     # 분류기(ConvNeXt) 모델
_class_names: List[str] = []           # 분류 결과 인덱스 → 사람이 읽는 클래스 이름
_type2group: Dict[str, str] = {}       # 세부 타입 → 상위 그룹 매핑 (선택적)
_models_loaded = False                 # 로드 성공 여부
_load_error: Optional[str] = None      # 로드 실패 시 원인 메시지


def get_models_status() -> Tuple[bool, Optional[str]]:
    """모델이 정상 로드됐는지 여부와 (실패했다면) 그 이유를 돌려준다."""
    return _models_loaded, _load_error


def get_detector_model():
    """메모리에 올려둔 탐지기(YOLO) 모델을 꺼내온다."""
    return _det_model


def get_classifier():
    """메모리에 올려둔 분류기(ConvNeXt) 모델을 꺼내온다."""
    return _classifier


def get_class_names() -> List[str]:
    """분류 결과 번호를 사람이 읽는 이름으로 바꿀 때 쓰는 이름 목록을 돌려준다."""
    return _class_names


def map_type_to_group(type_name: str) -> str:
    """세부 타입 이름을 상위 그룹 이름으로 바꿔준다 (매핑이 없으면 원래 이름 그대로)."""
    return _type2group.get(type_name, type_name)


def load_models(det_weight, cls_weight, cls_json) -> Tuple[bool, Optional[str]]:
    """첫 사용 시 한 번 호출: 탐지기·분류기·클래스 정보를 메모리에 적재한다."""
    global _det_model, _classifier, _class_names, _type2group
    global _models_loaded, _load_error

    # 1) 필요한 파일이 실제로 존재하는지 먼저 확인한다.
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

    # 2) 파일이 모두 있으면 실제로 모델을 메모리에 올린다.
    try:
        from ultralytics import YOLO

        _det_model = YOLO(str(det_weight))

        with open(cls_json, encoding="utf-8") as f:
            metadata = json.load(f)
        _class_names = metadata["classes"]
        _type2group = metadata.get("type2group", {})
        num_classes = len(_class_names)

        # 분류기의 마지막 출력층을 우리 클래스 개수에 맞게 교체한 뒤 가중치를 얹는다.
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
