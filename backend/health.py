"""
[상태 확인 API]
'GET /health' 요청에 응답하는 파일. 서버가 살아있는지, 그리고 SAR·EO 모델이 각각
정상적으로 로드됐는지를 알려준다. 프론트엔드가 각 페이지에서 "모델 로드됨/미로드"를
표시할 때 사용한다.
"""
from typing import Any, Dict

from fastapi import APIRouter

from backend.eo import api as eo_api
from backend.sar import api as sar_api

router = APIRouter(tags=["health"])


def get_app_health() -> Dict[str, Any]:
    """서버 상태와 SAR·EO 모델 로드 여부를 하나의 딕셔너리로 정리해 돌려준다."""
    sar_loaded, sar_error = sar_api.get_status()
    eo_loaded, eo_error = eo_api.get_status()
    return {
        "status": "ok",
        # 하위호환: 기존 SAR 페이지가 읽는 최상위 필드는 SAR 모델 상태를 가리킨다.
        "models_loaded": sar_loaded,
        "error": sar_error,
        # 도메인별 상태 (프론트에서 sar / eo 각각 확인할 때 사용).
        "sar": {"models_loaded": sar_loaded, "error": sar_error},
        "eo": {"models_loaded": eo_loaded, "error": eo_error},
    }


@router.get("/health")
def health():
    """GET /health 요청에 서버·모델 상태를 JSON으로 돌려준다."""
    return get_app_health()
