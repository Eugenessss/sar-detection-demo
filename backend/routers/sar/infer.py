from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.routers.sar.schemas import InferenceResponse
from backend.sar.services.inference_service import infer_upload
from backend.sar.services.model_registry import ModelUnavailableError

router = APIRouter(tags=["infer"])


def _raise_service_error(exc: ModelUnavailableError) -> None:
    raise HTTPException(status_code=503, detail=str(exc))


@router.post("/infer", response_model=InferenceResponse)
async def infer(
    tif: UploadFile = File(...),
    rotate_k: int = Form(0),
):
    try:
        return await infer_upload(tif=tif, rotate_k=rotate_k)
    except ModelUnavailableError as exc:
        _raise_service_error(exc)
