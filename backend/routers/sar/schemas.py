from typing import List, Optional

from pydantic import BaseModel


class DetectionItem(BaseModel):
    bbox: List[float]
    label: str
    det_conf: float
    cls_conf: float


class InferenceRun(BaseModel):
    rotate_k: int
    rotate_deg: int
    auto_rotation: bool
    detections: List[DetectionItem]
    n_det: int
    elapsed_sec: float


class InferenceResponse(InferenceRun):
    image_size: List[int]
    filename: str
    azimuth: Optional[int] = None
