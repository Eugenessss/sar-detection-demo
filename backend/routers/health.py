from fastapi import APIRouter

from backend.services.health_service import get_app_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return get_app_health()
