import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
from fastapi import UploadFile

from backend.infrastructure.temp_files import cleanup_paths, save_upload_to_temp
from backend.sar.detect import detect_on
from backend.sar.image import load_dom_rgb
from backend.sar.pipeline import run_full_inference
from backend.sar.rotation import parse_azi
from backend.sar.services.model_registry import ensure_models_loaded

DetectFn = Callable[[np.ndarray], List[Dict[str, Any]]]


@dataclass
class PreparedScene:
    scene: np.ndarray
    width: int
    height: int
    azimuth: Optional[int]
    filename: str
    temp_paths: List[Optional[Path]]


async def prepare_uploaded_scene(
    tif: UploadFile,
) -> PreparedScene:
    temp_paths: List[Optional[Path]] = []
    try:
        tif_suffix = Path(tif.filename or "upload.tif").suffix or ".tif"
        tif_path = await save_upload_to_temp(tif, suffix=tif_suffix)
        temp_paths.append(tif_path)

        filename = tif.filename or tif_path.name
        scene = load_dom_rgb(str(tif_path))
        height, width = scene.shape[:2]

        return PreparedScene(
            scene=scene,
            width=width,
            height=height,
            azimuth=parse_azi(filename),
            filename=filename,
            temp_paths=temp_paths,
        )
    except Exception:
        cleanup_paths(temp_paths)
        raise


def run_detection(
    scene: np.ndarray,
    azimuth: Optional[int],
    rotate_k: int,
    detect_fn: DetectFn,
) -> Dict[str, Any]:
    started_at = time.time()
    chosen_k = rotate_k % 4
    auto_rotation = False

    if azimuth is not None:
        chosen_k = int(round(azimuth / 90.0)) % 4
        auto_rotation = True

    detections = run_full_inference(
        scene,
        chosen_k,
        detect_fn=detect_fn,
    )

    return {
        "rotate_k": chosen_k,
        "rotate_deg": chosen_k * 90,
        "auto_rotation": auto_rotation,
        "detections": detections,
        "n_det": len(detections),
        "elapsed_sec": round(time.time() - started_at, 2),
    }


def build_inference_response(prepared: PreparedScene, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "image_size": [prepared.width, prepared.height],
        "filename": prepared.filename,
        "azimuth": prepared.azimuth,
        **result,
    }


async def infer_upload(
    tif: UploadFile,
    rotate_k: int,
) -> Dict[str, Any]:
    ensure_models_loaded()
    prepared = await prepare_uploaded_scene(tif)
    try:
        result = run_detection(prepared.scene, prepared.azimuth, rotate_k, detect_on)
        return build_inference_response(prepared, result)
    finally:
        cleanup_paths(prepared.temp_paths)
