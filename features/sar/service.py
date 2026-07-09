"""
[SAR 도메인 - 서비스]
업로드 이미지를 받아 SAR 추론 전체 흐름을 실행하는 순수 파이썬 함수.
예전 sar/api.py의 'HTTP 유스케이스'에서 FastAPI(UploadFile/HTTPException)를 걷어내고,
Streamlit 화면(view.py)이 직접 호출할 수 있게 만든 것이다.
흐름: 모델확인 → 임시저장 → 이미지 로딩 → 회전 결정 → 파이프라인 → 결과 조립.
"""
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from features.sar import models
from features.sar.detect import detect_on
from features.sar.image import load_dom_rgb
from features.sar.pipeline import run_full_inference
from features.sar.rotation import parse_azi
from shared.temp_files import cleanup_paths, save_bytes_to_temp


class ModelUnavailableError(RuntimeError):
    """모델이 아직 준비되지 않았을 때 발생시키는 도메인 전용 예외."""
    pass


def get_status() -> Tuple[bool, Optional[str]]:
    """모델이 로드됐는지 여부와 (실패 시) 이유를 돌려준다 (화면 상태 표시에 사용)."""
    return models.get_models_status()


def _ensure_models_loaded() -> None:
    """모델이 준비돼 있는지 확인하고, 아니면 안내 메시지와 함께 예외를 던진다."""
    loaded, err = get_status()
    if loaded:
        return
    raise ModelUnavailableError(
        f"모델이 로드되지 않았습니다. {err or ''} "
        "checkpoints/yolo_detector_yolo11n.pt, checkpoints/convnext_soc14_final.pth, "
        "results/convnext_soc14.json 파일을 확인하세요."
    )


def run_inference(file_bytes: bytes, filename: str, rotate_k: int) -> Dict[str, Any]:
    """업로드 바이트로 추론을 실행하고 결과(탐지 목록 + 메타 정보)를 돌려준다."""
    _ensure_models_loaded()

    temp_paths = []
    try:
        suffix = Path(filename or "upload.tif").suffix or ".tif"
        tif_path = save_bytes_to_temp(file_bytes, suffix=suffix)
        temp_paths.append(tif_path)

        name = filename or tif_path.name
        scene = load_dom_rgb(str(tif_path))
        height, width = scene.shape[:2]
        azimuth = parse_azi(name)   # 파일명에 방위각이 있으면 뽑아둔다

        started_at = time.time()
        chosen_k = rotate_k % 4
        auto_rotation = False
        # 파일명에 방위각이 있으면 그것으로 회전을 자동 결정하고, 없으면 사용자가 준 값을 쓴다.
        if azimuth is not None:
            chosen_k = int(round(azimuth / 90.0)) % 4
            auto_rotation = True

        detections = run_full_inference(scene, chosen_k, detect_fn=detect_on)

        return {
            "rotate_k": chosen_k,
            "rotate_deg": chosen_k * 90,
            "auto_rotation": auto_rotation,
            "detections": detections,
            "n_det": len(detections),
            "elapsed_sec": round(time.time() - started_at, 2),
            "image_size": [width, height],
            "filename": name,
            "azimuth": azimuth,
        }
    finally:
        cleanup_paths(temp_paths)   # 성공/실패와 무관하게 임시 파일은 반드시 정리
