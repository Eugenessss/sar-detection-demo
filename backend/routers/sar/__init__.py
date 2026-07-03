from fastapi import APIRouter

from backend.routers.sar import infer


router = APIRouter(prefix="/sar", tags=["sar"])
router.include_router(infer.router)
