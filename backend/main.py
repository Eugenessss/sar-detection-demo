"""
FastAPI 백엔드.
GET  /health      → 모델 로드 상태
GET  /annotations → sample_images/ 에 보관된 XML 목록
POST /infer       → 탐지+분류+채점
  - tif: 업로드 TIF (필수)
  - xml: 업로드 XML (선택 — 없으면 sample_images/{stem}.xml 자동 매칭)
  - rotate_k: 수동 회전 폴백 (0~3)
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import DET_WEIGHT, CLS_WEIGHT, CLS_JSON
from backend import models
from backend.routers import health, annotations, infer


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok, err = models.load_models(DET_WEIGHT, CLS_WEIGHT, CLS_JSON)
    if not ok:
        logging.getLogger(__name__).warning("모델 로드 실패: %s", err)
    yield


app = FastAPI(title="DOM SAR 차량 탐지 데모", lifespan=lifespan)
app.include_router(health.router)
app.include_router(annotations.router)
app.include_router(infer.router)
