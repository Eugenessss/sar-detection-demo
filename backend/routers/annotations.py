from fastapi import APIRouter
from backend.config import ANNOTATION_DIR

router = APIRouter(tags=["annotations"])


@router.get("/annotations")
def list_annotations():
    if not ANNOTATION_DIR.exists():
        return {"xmls": []}
    xmls = sorted(f.name for f in ANNOTATION_DIR.iterdir() if f.suffix.lower() == ".xml")
    return {"xmls": xmls}
