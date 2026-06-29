import os
import time
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from backend import models
from backend.config import ANNOTATION_DIR
from backend.image import load_dom_rgb
from backend.rotation import parse_azi
from backend.gt import load_gt
from backend.pipeline import correct_rotation, run_full_inference
from backend.detect import detect_on, detect_on_sahi

router = APIRouter(tags=["infer"])


def _require_models():
    loaded, err = models.get_models_status()
    if not loaded:
        raise HTTPException(
            status_code=503,
            detail=(
                f"모델이 로드되지 않았습니다. {err or ''} "
                "backend/checkpoints/yolo_detector_yolo11n.pt, "
                "backend/checkpoints/convnext_soc14_final.pth, "
                "backend/results/convnext_soc14.json 파일을 확인하세요."
            ),
        )


async def _prepare(tif: UploadFile, xml: Optional[UploadFile]):
    """업로드 저장 + 장면/GT/방위각 준비. (scene, W, H, gt, azi, orig, xml_matched, tmps) 반환."""
    suffix = Path(tif.filename or "upload.tif").suffix or ".tif"
    tmp_tif = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_tif.write(await tif.read()); tmp_tif.flush(); tmp_tif.close()
    img_path = Path(tmp_tif.name)
    orig = tif.filename or img_path.name

    tmp_xml = None
    xml_path = None
    if xml is not None:
        tmp_xml = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
        tmp_xml.write(await xml.read()); tmp_xml.flush(); tmp_xml.close()
        xml_path = tmp_xml.name
    else:
        auto = ANNOTATION_DIR / (Path(orig).stem + ".xml")
        if auto.exists():
            xml_path = str(auto)

    scene = load_dom_rgb(str(img_path))
    H, W = scene.shape[:2]

    gt = None
    if xml_path:
        try:
            gt = load_gt(xml_path)
        except Exception:
            gt = None

    azi = parse_azi(orig)
    return dict(scene=scene, W=W, H=H, gt=gt, azi=azi, orig=orig,
                xml_matched=xml_path is not None, tmps=[tmp_tif, tmp_xml])


def _cleanup(tmps):
    for t in tmps:
        if t is not None:
            try:
                os.unlink(t.name)
            except Exception:
                pass


def _run(scene, gt, azi, rotate_k, detect_fn):
    """한 가지 탐지 방식으로 회전결정→탐지+분류→채점. 결과 dict 반환."""
    t0 = time.time()
    chosen_k = rotate_k
    auto = False
    cached = None
    if azi is not None and gt:
        chosen_k, _, _, _, cached = correct_rotation(scene, gt, azi, detect_fn=detect_fn)
        auto = True
    elif azi is not None:
        chosen_k = int(round(azi / 90.0)) % 4
        auto = True

    dets, metrics, missed = run_full_inference(scene, chosen_k, gt, cached, detect_fn=detect_fn)
    n_matched = metrics["n_matched"] if metrics else 0
    return {
        "rotate_k":      chosen_k,
        "rotate_deg":    chosen_k * 90,
        "auto_rotation": auto,
        "detections":    dets,
        "missed":        missed,
        "metrics":       metrics,
        "n_det":         len(dets),
        "n_fp":          len(dets) - n_matched,
        "elapsed_sec":   round(time.time() - t0, 2),
    }


@router.post("/infer")
async def infer(
    tif:      UploadFile           = File(...),
    xml:      Optional[UploadFile] = File(None),
    rotate_k: int                  = Form(0),
):
    _require_models()
    p = await _prepare(tif, xml)
    try:
        res = _run(p["scene"], p["gt"], p["azi"], rotate_k, detect_on)
        return {
            "image_size":  [p["W"], p["H"]],
            "filename":    p["orig"],
            "azimuth":     p["azi"],
            "xml_matched": p["xml_matched"],
            **res,
        }
    finally:
        _cleanup(p["tmps"])


@router.post("/compare")
async def compare(
    tif:      UploadFile           = File(...),
    xml:      Optional[UploadFile] = File(None),
    rotate_k: int                  = Form(0),
):
    """SAHI vs 수동타일링+배치 — 같은 이미지로 둘 다 실행해 함께 반환."""
    _require_models()
    p = await _prepare(tif, xml)
    try:
        sahi   = _run(p["scene"], p["gt"], p["azi"], rotate_k, detect_on_sahi)
        manual = _run(p["scene"], p["gt"], p["azi"], rotate_k, detect_on)
        return {
            "image_size":  [p["W"], p["H"]],
            "filename":    p["orig"],
            "azimuth":     p["azi"],
            "xml_matched": p["xml_matched"],
            "sahi":        sahi,
            "manual":      manual,
        }
    finally:
        _cleanup(p["tmps"])
