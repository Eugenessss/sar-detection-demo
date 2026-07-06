"""
[백엔드 진입점]
FastAPI 앱을 만들고, 각 도메인의 라우터(/health, /sar, /eo)를 하나로 조립하는 파일.
'uvicorn backend.main:app'으로 실행하면 여기의 app이 서버로 뜬다.
앱이 켜질 때(lifespan) 모델을 미리 메모리에 올려두어, 요청마다 다시 로드하지 않게 한다.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend import health
from backend.db.api import router as db_router
from backend.eo.api import load_default_models as load_eo_models, router as eo_router
from backend.sar.api import load_default_models as load_sar_models, router as sar_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱이 켜질 때 딱 한 번 실행: SAR·EO 모델을 미리 로드한다 (실패해도 서버는 뜨고 경고만 남김)."""
    log = logging.getLogger(__name__)
    for name, loader in [("SAR", load_sar_models), ("EO", load_eo_models)]:
        ok, err = loader()
        if not ok:
            log.warning("%s 모델 로드 실패: %s", name, err)
    yield


app = FastAPI(title="청출어람 — EO/SAR 위성영상 기반 표적 후보 탐지 및 판독 지원 서비스", lifespan=lifespan)
app.include_router(health.router)   # GET /health
app.include_router(sar_router)      # POST /sar/infer
app.include_router(eo_router)       # POST /eo/infer
app.include_router(db_router)       # /db (testdb 조회)
