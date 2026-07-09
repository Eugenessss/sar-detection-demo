"""
[EO 도메인 - 서비스]
업로드 이미지를 받아 EO 탐지 흐름을 실행하는 순수 파이썬 함수.
예전 eo/api.py의 'HTTP 유스케이스'에서 FastAPI를 걷어내 view.py가 직접 호출하게 만든 것이다.
흐름: 모델확인 → 임시저장 → 크기확인 → 탐지 → 결과 조립.
"""
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from features.eo import models
from features.eo.detect import detect_on
from shared.temp_files import cleanup_paths, save_bytes_to_temp


class ModelUnavailableError(RuntimeError):
    """EO 모델이 아직 준비되지 않았을 때 발생시키는 예외."""
    pass


def get_status() -> Tuple[bool, Optional[str]]:
    """EO 모델이 로드됐는지 여부와 (실패 시) 이유를 돌려준다."""
    return models.get_models_status()


def _ensure_models_loaded() -> None:
    """EO 모델이 준비돼 있는지 확인하고, 아니면 안내와 함께 예외를 던진다."""
    loaded, err = get_status()
    if loaded:
        return
    raise ModelUnavailableError(
        f"EO 모델이 로드되지 않았습니다. {err or ''} checkpoints/best.pt 파일을 확인하세요."
    )


def run_inference(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """업로드 바이트로 EO 탐지를 실행하고 결과를 돌려준다."""
    _ensure_models_loaded()

    temp_paths = []
    try:
        suffix = Path(filename or "upload.jpg").suffix or ".jpg"
        image_path = save_bytes_to_temp(file_bytes, suffix=suffix)
        temp_paths.append(image_path)

        started_at = time.time()
        # 결과 표시용으로 원본 이미지 크기(가로, 세로)를 읽어둔다.
        with Image.open(image_path) as im:
            width, height = im.size

        detections = detect_on(str(image_path))

        return {
            "detections": detections,
            "n_det": len(detections),
            "elapsed_sec": round(time.time() - started_at, 2),
            "image_size": [width, height],
            "filename": filename or image_path.name,
        }
    finally:
        cleanup_paths(temp_paths)   # 성공/실패와 무관하게 임시 파일은 반드시 정리
