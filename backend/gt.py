import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple, Optional

from backend import models as _m


def load_gt(xml_path: str) -> List[Tuple[List[float], str]]:
    gt = []
    for obj in ET.parse(xml_path).getroot().findall("object"):
        bb = obj.find("bndbox")
        box = [float(bb.find(t).text) for t in ["xmin", "ymin", "xmax", "ymax"]]
        typ = obj.find("type").text.strip()
        grp = _m._type2group.get(typ, typ)
        gt.append((box, grp))
    return gt


def infer_gt_xml(img_path: str) -> Optional[str]:
    """이미지 경로에서 GT xml 경로 자동 유추 (노트북 규칙)."""
    p = img_path.replace("/Result/", "/Annotation/").replace("\\Result\\", "\\Annotation\\")
    p = p.replace(".tif", ".xml").replace(".png", ".xml")
    return p if Path(p).exists() else None


def iou(a: List[float], b: List[float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter + 1e-9)
