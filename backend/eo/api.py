"""
[EO 도메인 - API 창구 (하나로 합친 파일)]
프론트엔드에서 들어온 'POST /eo/infer' 요청을 받아 처리하는 EO 도메인의 대표 파일.
sar/api.py와 같은 구성으로, 초보자가 흐름을 위→아래로 따라갈 수 있게 한 파일에 모아두었다.

읽는 순서(위→아래):
  1) 응답 스키마      : 결과를 어떤 모양(JSON)으로 돌려줄지 정의
  2) 모델 로드/상태   : 모델이 준비됐는지 확인
  3) 추론 use case    : 업로드 저장 → 크기 확인 → 탐지 → 응답 조립
  4) HTTP 엔드포인트  : 위 흐름을 실제 URL(/eo/infer)에 연결
"""
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from backend.eo import models
from backend.eo.config import DET_WEIGHT
from backend.eo.detect import detect_on
from backend.temp_files import cleanup_paths, save_upload_to_temp

router = APIRouter(prefix="/eo", tags=["eo"])


# =====================================================================
# 1) 응답 스키마
# =====================================================================

class EoDetectionItem(BaseModel):
    """탐지된 표적 하나 (위치·클래스 이름·신뢰도)."""
    bbox: List[float]
    label: str
    conf: float


class EoInferenceResponse(BaseModel):
    """프론트로 반환되는 EO 추론 응답."""
    detections: List[EoDetectionItem]
    n_det: int
    elapsed_sec: float
    image_size: List[int]
    filename: str


# =====================================================================
# 2) 모델 로드 / 상태 확인
# =====================================================================

class ModelUnavailableError(RuntimeError):
    """EO 모델이 아직 준비되지 않았을 때 발생시키는 예외."""
    pass


def load_default_models() -> Tuple[bool, Optional[str]]:
    """설정에 적힌 경로로 EO 모델을 로드한다 (앱 시작 시 main.py가 호출)."""
    return models.load_models(DET_WEIGHT)


def get_status() -> Tuple[bool, Optional[str]]:
    """EO 모델이 로드됐는지 여부와 (실패 시) 이유를 돌려준다 (health 체크에서 사용)."""
    return models.get_models_status()


def ensure_models_loaded() -> None:
    """EO 모델이 준비돼 있는지 확인하고, 아니면 안내와 함께 예외를 던진다."""
    loaded, err = get_status()
    if loaded:
        return
    detail = (
        f"EO 모델이 로드되지 않았습니다. {err or ''} "
        "backend/checkpoints/best.pt 파일을 확인하세요."
    )
    raise ModelUnavailableError(detail)


# =====================================================================
# 3) 추론 use case — 업로드부터 응답 조립까지
# =====================================================================

async def infer_upload(image: UploadFile) -> Dict[str, Any]:
    """추론 전체 흐름: 모델확인 → 임시저장 → 크기확인 → 탐지 → 응답조립."""
    ensure_models_loaded()

    temp_paths: List[Optional[Path]] = []
    try:
        suffix = Path(image.filename or "upload.jpg").suffix or ".jpg"
        image_path = await save_upload_to_temp(image, suffix=suffix)
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
            "filename": image.filename or image_path.name,
        }
    finally:
        cleanup_paths(temp_paths)   # 성공/실패와 무관하게 임시 파일은 반드시 정리


# =====================================================================
# 4) HTTP 엔드포인트
# =====================================================================

@router.post("/infer", response_model=EoInferenceResponse)
async def infer(image: UploadFile = File(...)):
    """POST /eo/infer 요청을 받아 EO 탐지를 실행하고 결과를 돌려준다."""
    try:
        return await infer_upload(image=image)
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
