from typing import Optional, Tuple

from backend.sar import models
from backend.sar.config import CLS_JSON, CLS_WEIGHT, DET_WEIGHT


class ModelUnavailableError(RuntimeError):
    pass


def load_default_models() -> Tuple[bool, Optional[str]]:
    return models.load_models(DET_WEIGHT, CLS_WEIGHT, CLS_JSON)


def get_status() -> Tuple[bool, Optional[str]]:
    return models.get_models_status()


def ensure_models_loaded() -> None:
    loaded, err = get_status()
    if loaded:
        return

    detail = (
        f"모델이 로드되지 않았습니다. {err or ''} "
        "backend/checkpoints/yolo_detector_yolo11n.pt, "
        "backend/checkpoints/convnext_soc14_final.pth, "
        "backend/results/convnext_soc14.json 파일을 확인하세요."
    )
    raise ModelUnavailableError(detail)
