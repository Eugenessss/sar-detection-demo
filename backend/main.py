import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.routers import health
from backend.routers.eo import router as eo_router
from backend.routers.sar import router as sar_router
from backend.sar.services.model_registry import load_default_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok, err = load_default_models()
    if not ok:
        logging.getLogger(__name__).warning("모델 로드 실패: %s", err)
    yield


app = FastAPI(title="DOM SAR 차량 탐지 데모", lifespan=lifespan)
app.include_router(health.router)
app.include_router(sar_router)
app.include_router(eo_router)
