from fastapi import APIRouter
from backend import models

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    loaded, err = models.get_models_status()
    return {"status": "ok", "models_loaded": loaded, "error": err}
