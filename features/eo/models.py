"""
[EO 도메인 - 모델 보관소]
EO 탐지기(YOLO best.pt)를 앱이 켜질 때 한 번 메모리에 올려두고, 이후 요청마다 꺼내 쓰도록
보관하는 파일. 클래스 이름은 가중치 안에 들어 있으므로 모델에서 그대로 읽어온다.
"""
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)

# "한 번 로드해서 계속 재사용"하는 실제 저장 공간.
_det_model = None                   # 탐지기(YOLO) 모델
_class_names: Dict[int, str] = {}   # 클래스 번호 → 이름 (모델에 내장된 값)
_models_loaded = False              # 로드 성공 여부
_load_error: Optional[str] = None   # 로드 실패 시 원인 메시지


def get_models_status() -> Tuple[bool, Optional[str]]:
    """모델이 정상 로드됐는지 여부와 (실패했다면) 그 이유를 돌려준다."""
    return _models_loaded, _load_error


def get_detector_model():
    """메모리에 올려둔 EO 탐지기(YOLO) 모델을 꺼내온다."""
    return _det_model


def get_class_names() -> Dict[int, str]:
    """클래스 번호를 사람이 읽는 이름으로 바꿀 때 쓰는 이름 표를 돌려준다."""
    return _class_names


def load_models(det_weight) -> Tuple[bool, Optional[str]]:
    """앱 시작 시 한 번 호출: EO 탐지기 가중치를 메모리에 적재한다."""
    global _det_model, _class_names, _models_loaded, _load_error

    # 1) 가중치 파일이 실제로 있는지 먼저 확인한다.
    if not Path(det_weight).exists():
        _models_loaded = False
        _load_error = f"EO 탐지 가중치가 없습니다: {det_weight}"
        log.error(_load_error)
        return False, _load_error

    # 2) 파일이 있으면 실제로 모델을 메모리에 올린다.
    try:
        from ultralytics import YOLO

        _det_model = YOLO(str(det_weight))
        _class_names = dict(_det_model.names)   # {0: 'plane', 1: 'ship', ...} 형태
        _models_loaded = True
        _load_error = None
        log.info("EO 모델 로드 완료. 클래스 수: %d", len(_class_names))
        return True, None

    except Exception as exc:
        _models_loaded = False
        _load_error = f"EO 모델 로드 실패: {exc}"
        log.exception(_load_error)
        return False, _load_error
