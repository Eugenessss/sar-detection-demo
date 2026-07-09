"""
[공용 - 시각화]
탐지 결과(박스 목록)를 이미지 위에 클래스별 색상 박스와 라벨로 그려주는 파일.
SAR·EO 페이지가 똑같이 사용하는 진짜 공용 기능만 남겼다.
(이미지 '로딩'은 도메인마다 방식이 달라 각 feature의 image.py에 있다.)
화면에 크게 표시할 때 너무 큰 이미지는 적당히 줄인다.
"""
import hashlib
from typing import Dict, List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LABEL_COLORS = [
    "#F94144",
    "#F3722C",
    "#F8961E",
    "#F9C74F",
    "#90BE6D",
    "#43AA8B",
    "#4D908E",
    "#577590",
    "#277DA1",
    "#9B5DE5",
    "#F15BB5",
    "#00BBF9",
    "#00F5D4",
    "#B8F2E6",
]


def _color_for_label(label: str) -> str:
    """라벨 이름을 항상 같은 색상으로 매핑한다."""
    digest = hashlib.blake2s(label.encode("utf-8"), digest_size=2).digest()
    color_index = int.from_bytes(digest, "big") % len(LABEL_COLORS)
    return LABEL_COLORS[color_index]


def _text_color_for_background(hex_color: str) -> str:
    """색상 밝기에 맞춰 라벨 글자를 검정/흰색 중 더 잘 보이는 쪽으로 고른다."""
    red = int(hex_color[1:3], 16)
    green = int(hex_color[3:5], 16)
    blue = int(hex_color[5:7], 16)
    luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
    return "#000000" if luminance > 150 else "#FFFFFF"


def draw_boxes(scene_rgb: np.ndarray, detections: List[Dict]) -> Image.Image:
    """이미지 위에 탐지된 박스와 라벨을 그려서 화면에 표시할 이미지를 만든다."""
    img = Image.fromarray(scene_rgb).convert("RGB")
    # 너무 큰 이미지는 화면 표시용으로 최대 1200px까지 줄인다 (박스 좌표도 같은 비율로 축소).
    max_side = 2048
    scale = 1.0
    if max(img.width, img.height) > max_side:
        scale = max_side / max(img.width, img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

    draw = ImageDraw.Draw(img)
    font_size = max(10, int(14 * scale))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()   # 시스템 폰트가 없으면 기본 폰트로 대체

    for det in detections:
        bx1, by1, bx2, by2 = [v * scale for v in det["bbox"]]
        raw_label = str(det["label"])
        color = _color_for_label(raw_label)
        text_color = _text_color_for_background(color)
        draw.rectangle([bx1, by1, bx2, by2], outline=color, width=max(1, int(2 * scale)))
        # 분류 확신도가 있으면 라벨 옆에 함께 표시한다.
        # 신뢰도는 도메인에 따라 키 이름이 다르다 (EO: conf, SAR: cls_conf). 있는 쪽을 읽는다.
        conf = det.get("conf", det.get("cls_conf"))
        if conf is None:
            label = raw_label
        else:
            label = f"{raw_label} {conf:.2f}"
        # 글자가 잘 보이도록 라벨 색상 배경을 깔아준다.
        try:
            text_box = draw.textbbox((bx1, by1 - font_size - 2), label, font=font)
            draw.rectangle(text_box, fill=color)
        except Exception:
            pass
        draw.text((bx1, by1 - font_size - 2), label, fill=text_color, font=font)

    return img
