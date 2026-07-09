"""
[EO 도메인 - 서비스]
업로드 이미지를 받아 EO 탐지 흐름을 실행하는 순수 파이썬 함수.
화면(view.py)이 직접 호출하며, 화면 표시에 필요한 것(탐지 목록·원본 색 이미지)까지
한 번에 담아 돌려준다.
흐름: 모델확인 → 임시저장 → 이미지 로딩 → 탐지 → 결과 조립.
"""
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from features.eo import models
from features.eo.detect import detect_on
from features.eo.image import load_image_rgb
from shared.temp_files import cleanup_paths, save_bytes_to_temp


class ModelUnavailableError(RuntimeError):
    """EO 모델이 아직 준비되지 않았을 때 발생시키는 예외."""
    pass


@dataclass
class EoInferenceResult:
    """EO 탐지 한 번의 결과. 화면이 그대로 표시할 수 있는 형태로 담는다."""
    detections: List[Dict[str, Any]]   # 탐지 목록 [{bbox, label, conf}, ...]
    elapsed_sec: float                 # 탐지 소요 시간
    filename: str                      # 업로드 파일 이름
    scene: np.ndarray                  # 원본 색 그대로의 RGB 이미지 (화면 표시용)


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


def run_inference(file_bytes: bytes, filename: str) -> EoInferenceResult:
    """업로드 바이트로 EO 탐지를 실행하고 결과(탐지 목록 + 표시용 이미지)를 돌려준다."""
    _ensure_models_loaded()

    temp_paths = []
    try:
        suffix = Path(filename or "upload.jpg").suffix or ".jpg"
        image_path = save_bytes_to_temp(file_bytes, suffix=suffix)
        temp_paths.append(image_path)

        # 화면 표시용으로 원본 색 그대로 읽어둔다 (탐지와 같은 파일을 한 번만 디코드).
        scene = load_image_rgb(image_path)
        if scene is None:
            raise ValueError(f"이미지 파일을 읽을 수 없습니다: {filename}")

        started_at = time.time()
        detections = detect_on(str(image_path))

        return EoInferenceResult(
            detections=detections,
            elapsed_sec=round(time.time() - started_at, 2),
            filename=filename or image_path.name,
            scene=scene,
        )
    finally:
        cleanup_paths(temp_paths)   # 성공/실패와 무관하게 임시 파일은 반드시 정리
