"""
[SAR 도메인 - API 창구 (하나로 합친 파일)]
프론트엔드에서 들어온 'POST /sar/infer' 요청을 받아 처리하는 SAR 도메인의 대표 파일.
원래 여러 계층(라우터/스키마/서비스/모델 상태)으로 나뉘어 있던 것을, 초보자가 흐름을
한눈에 따라갈 수 있도록 한 파일에 위→아래 순서로 모아두었다.

읽는 순서(위→아래):
  1) 응답 스키마      : 결과를 어떤 모양(JSON)으로 돌려줄지 정의
  2) 모델 로드/상태   : 모델이 준비됐는지 확인하고, 안 됐으면 503 에러를 낼 근거를 만든다
  3) 추론 use case    : 업로드 저장 → 이미지 로딩 → 파이프라인 실행 → 응답 조립의 실제 흐름
  4) HTTP 엔드포인트  : 위 흐름을 실제 URL(/sar/infer)에 연결
"""
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.sar import models
from backend.sar.config import CLS_JSON, CLS_WEIGHT, DET_WEIGHT
from backend.sar.detect import detect_on
from backend.sar.image import load_dom_rgb
from backend.sar.pipeline import run_full_inference
from backend.sar.rotation import parse_azi
from backend.temp_files import cleanup_paths, save_upload_to_temp

router = APIRouter(prefix="/sar", tags=["sar"])

# 탐지 함수의 형태(이미지 배열을 받아 박스 목록을 돌려줌)를 이름으로 정의해 둔 것.
DetectFn = Callable[[np.ndarray], List[Dict[str, Any]]]


# =====================================================================
# 1) 응답 스키마 — 결과 JSON의 모양을 정의한다.
# =====================================================================

class DetectionItem(BaseModel):
    """탐지된 차량 하나에 대한 정보 (위치·라벨·확신도)."""
    bbox: List[float]
    label: str
    det_conf: float
    cls_conf: float


class InferenceRun(BaseModel):
    """한 번의 추론 실행 결과 (회전 정보 + 탐지 목록 + 소요 시간)."""
    rotate_k: int
    rotate_deg: int
    auto_rotation: bool
    detections: List[DetectionItem]
    n_det: int
    elapsed_sec: float


class InferenceResponse(InferenceRun):
    """프론트로 최종 반환되는 응답 (실행 결과 + 이미지 크기·파일명 등 메타 정보)."""
    image_size: List[int]
    filename: str
    azimuth: Optional[int] = None


# =====================================================================
# 2) 모델 로드 / 상태 확인
# =====================================================================

class ModelUnavailableError(RuntimeError):
    """모델이 아직 준비되지 않았을 때 발생시키는 도메인 전용 예외."""
    pass


def load_default_models() -> Tuple[bool, Optional[str]]:
    """설정 파일에 적힌 경로로 기본 모델을 로드한다 (앱 시작 시 main.py가 호출)."""
    return models.load_models(DET_WEIGHT, CLS_WEIGHT, CLS_JSON)


def get_status() -> Tuple[bool, Optional[str]]:
    """모델이 로드됐는지 여부와 (실패 시) 이유를 돌려준다 (health 체크에서 사용)."""
    return models.get_models_status()


def ensure_models_loaded() -> None:
    """모델이 준비돼 있는지 확인하고, 아니면 안내 메시지와 함께 예외를 던진다."""
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


# =====================================================================
# 3) 추론 use case — 업로드부터 응답 조립까지의 실제 흐름
# =====================================================================

@dataclass
class PreparedScene:
    """업로드 이미지를 추론 직전 상태로 준비해 담아두는 꾸러미."""
    scene: np.ndarray
    width: int
    height: int
    azimuth: Optional[int]
    filename: str
    temp_paths: List[Optional[Path]]


async def prepare_uploaded_scene(tif: UploadFile) -> PreparedScene:
    """업로드 파일을 임시 저장하고 이미지로 읽어들여, 추론에 필요한 정보를 준비한다."""
    temp_paths: List[Optional[Path]] = []
    try:
        tif_suffix = Path(tif.filename or "upload.tif").suffix or ".tif"
        tif_path = await save_upload_to_temp(tif, suffix=tif_suffix)
        temp_paths.append(tif_path)

        filename = tif.filename or tif_path.name
        scene = load_dom_rgb(str(tif_path))
        height, width = scene.shape[:2]

        return PreparedScene(
            scene=scene,
            width=width,
            height=height,
            azimuth=parse_azi(filename),   # 파일명에 방위각이 있으면 뽑아둔다
            filename=filename,
            temp_paths=temp_paths,
        )
    except Exception:
        cleanup_paths(temp_paths)   # 중간에 실패하면 임시 파일을 정리하고 예외를 넘긴다
        raise


def run_detection(
    scene: np.ndarray,
    azimuth: Optional[int],
    rotate_k: int,
    detect_fn: DetectFn,
) -> Dict[str, Any]:
    """회전 각도를 정하고 파이프라인을 돌린 뒤, 결과를 요약 정보와 함께 묶어 돌려준다."""
    started_at = time.time()
    chosen_k = rotate_k % 4
    auto_rotation = False

    # 파일명에 방위각이 있으면 그것으로 회전을 자동 결정하고, 없으면 사용자가 준 값을 쓴다.
    if azimuth is not None:
        chosen_k = int(round(azimuth / 90.0)) % 4
        auto_rotation = True

    detections = run_full_inference(
        scene,
        chosen_k,
        detect_fn=detect_fn,
    )

    return {
        "rotate_k": chosen_k,
        "rotate_deg": chosen_k * 90,
        "auto_rotation": auto_rotation,
        "detections": detections,
        "n_det": len(detections),
        "elapsed_sec": round(time.time() - started_at, 2),
    }


def build_inference_response(prepared: PreparedScene, result: Dict[str, Any]) -> Dict[str, Any]:
    """추론 결과에 이미지 크기·파일명 등 메타 정보를 더해 최종 응답 형태로 조립한다."""
    return {
        "image_size": [prepared.width, prepared.height],
        "filename": prepared.filename,
        "azimuth": prepared.azimuth,
        **result,
    }


async def infer_upload(tif: UploadFile, rotate_k: int) -> Dict[str, Any]:
    """추론 전체 흐름을 한 줄로 잇는 함수: 모델확인 → 이미지준비 → 탐지 → 응답조립."""
    ensure_models_loaded()
    prepared = await prepare_uploaded_scene(tif)
    try:
        result = run_detection(prepared.scene, prepared.azimuth, rotate_k, detect_on)
        return build_inference_response(prepared, result)
    finally:
        cleanup_paths(prepared.temp_paths)   # 성공/실패와 무관하게 임시 파일은 반드시 정리


# =====================================================================
# 4) HTTP 엔드포인트 — 위 흐름을 실제 URL에 연결
# =====================================================================

@router.post("/infer", response_model=InferenceResponse)
async def infer(
    tif: UploadFile = File(...),
    rotate_k: int = Form(0),
):
    """POST /sar/infer 요청을 받아 추론 흐름을 실행하고 결과를 돌려준다."""
    try:
        return await infer_upload(tif=tif, rotate_k=rotate_k)
    except ModelUnavailableError as exc:
        # 도메인 예외를 HTTP 503(서비스 준비 안 됨)으로 바꿔 프론트에 전달한다.
        raise HTTPException(status_code=503, detail=str(exc))
