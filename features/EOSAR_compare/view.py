"""
[EO/SAR 비교 분석 화면]
S3의 original_image/(원본)와 result_image/(탐지 결과) 이미지를 나란히 놓고
같은 지역·같은 시각의 EO와 SAR을 비교 판독하는 페이지.

배치 (제목 영역만 shared.ui_chrome 커맨드바, 나머지는 Streamlit 기본 위젯):
  - 상단 카드: 지역 드롭다운(개풍군/원산시) + 촬영 시각(연/월/일/시 — 시는 2시간 단위) 선택,
    맨 오른쪽에 HTML 보고서 저장 버튼. 기본값은 S3 사진 중 가장 최근 촬영 시각.
  - 본문: EO 행(원본 | 분석)을 위에, SAR 행(원본 | 분석)을 아래에 배치.
    한 화면에 다 보이도록 각 칸은 [이미지 | 메모]를 좌우로 붙여 세로 길이를 줄였다.
  - 해당 이미지가 없는 칸은 ARGOS 로고와 안내로 대신한다 (예: 같은 시각 SAR 없음).

HTML 보고서:
  - 다운로드 버튼으로 자가완결형(이미지 base64 내장) HTML 파일을 저장한다.
    기본정보·영상 보유 현황 표 + 4개 비교 패널(각 메모 포함)을 클래식하고 컴팩트한
    문서 양식으로 구성하며, 없는 영상은 보고서에도 "영상 없음" 패널로 표시된다.

이미지 매칭은 파일명 메타데이터로 한다:
  "자산명_지역명_지역ID_센서_YYYY-MM-DD 시각.확장자" 형식의 파일명을 해석해
  (지역, 촬영시각, 센서)가 선택값과 일치하는 S3 객체를 찾는다. 파일명 끝의 공백이나
  시각 자리수 차이(1000/100000/1000000)도 eosar 페이지와 같은 규칙으로 흡수한다.
"""
import base64
import html as html_lib
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import streamlit as st
from PIL import Image

from features.sar.image import normalize_to_uint8_rgb
from shared import s3_store
from shared.ui_chrome import bracket_panel, render_command_bar

Image.MAX_IMAGE_PIXELS = None   # 대형 SAR TIF도 열 수 있도록 픽셀 수 제한 해제

_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "argos_logo.png"          # 빈 칸 표시용
_LOGO_SMALL_PATH = Path(__file__).resolve().parent / "assets" / "argos_logo_small.png"  # 헤더용

_REGIONS = ["개풍군", "원산시"]          # 지역 선택 드롭다운 항목
_HOURS = list(range(0, 24, 2))           # 촬영 시각은 2시간 간격 (00, 02, ..., 22시)


# =====================================================================
# 0) 파일명 → 메타데이터 해석 (eosar 페이지와 같은 유연한 규칙)
# =====================================================================

def _parse_captured_time(date_part: str, time_part: str) -> Optional[datetime]:
    """날짜("YYYY-MM-DD")와 시각 숫자를 datetime으로 바꾼다.

    시각 자리수가 들쭉날쭉해도 받아준다:
      4자리 "1000" → 10:00:00 / 6자리 "100000" → 10:00:00 / 7자리 이상 → 앞 6자리만 사용.
    """
    digits = re.sub(r"\D", "", time_part)
    if len(digits) == 4:        # HHMM
        digits += "00"
    elif len(digits) >= 6:      # HHMMSS (넘치는 뒷자리는 무시)
        digits = digits[:6]
    else:
        return None
    try:
        return datetime.strptime(f"{date_part} {digits}", "%Y-%m-%d %H%M%S")
    except ValueError:
        return None


def parse_image_meta(filename: Optional[str]) -> Optional[Dict[str, Any]]:
    """파일명에서 (자산, 지역, 지역ID, 센서, 촬영시각)을 뽑는다. 형식이 다르면 None."""
    if not filename:
        return None
    parts = Path(filename).stem.split("_")
    # "YYYY-MM-DD_100000"처럼 시각 앞을 밑줄로 쓴 경우 날짜와 시각을 도로 합쳐준다.
    if len(parts) == 6 and re.fullmatch(r"\d{4,}", parts[5].strip()):
        parts = parts[:4] + [f"{parts[4]} {parts[5]}"]
    if len(parts) != 5:
        return None

    asset_name, region_name, region_id_raw, sensor_raw, time_raw = parts
    if not region_id_raw.isdigit():
        return None
    sensor_type = sensor_raw.upper()
    if sensor_type not in ("EO", "SAR"):
        return None

    time_tokens = time_raw.split()
    if len(time_tokens) != 2:
        return None
    captured_time = _parse_captured_time(time_tokens[0], time_tokens[1])
    if captured_time is None:
        return None

    return {
        "asset_name": asset_name,
        "region_name": region_name,
        "region_id": int(region_id_raw),
        "sensor_type": sensor_type,
        "captured_time": captured_time,
    }


# =====================================================================
# 1) S3 카탈로그 — 두 폴더의 객체를 (지역, 시각, 센서, 종류)로 색인한다
# =====================================================================

@st.cache_data(ttl=60, show_spinner=False)
def _load_catalog() -> Dict[str, Any]:
    """S3의 original_image/·result_image/ 객체를 파일명 메타데이터로 색인한다 (60초 캐시).

    돌려주는 값:
      index  : {(지역, 촬영시각 ISO문자열, 센서, 종류): S3 키}  (종류: original | result)
      assets : {지역: 자산명}  (보고서 표기용)
      latest : 가장 최근 촬영 시각(datetime)과 그 지역 — 화면 기본값으로 사용
      error  : 목록 조회 실패 시 원인 메시지
    """
    index: Dict[Any, str] = {}
    assets: Dict[str, str] = {}
    latest_time: Optional[datetime] = None
    latest_region: Optional[str] = None

    try:
        entries = [
            ("original", s3_store.list_keys("original_image/")),
            ("result", s3_store.list_keys("result_image/")),
        ]
    except Exception as exc:
        return {
            "index": {}, "assets": {},
            "latest_time": None, "latest_region": None, "error": str(exc),
        }

    for kind, keys in entries:
        for key in keys:
            name = key.split("/", 1)[1] if "/" in key else key
            meta = parse_image_meta(name)
            if not name or meta is None:
                continue   # 폴더 자체 키(빈 이름)나 image_id 이름(8224.png 등)은 건너뛴다
            lookup = (meta["region_name"], meta["captured_time"].isoformat(), meta["sensor_type"], kind)
            index.setdefault(lookup, key)
            assets.setdefault(meta["region_name"], meta["asset_name"])
            if latest_time is None or meta["captured_time"] > latest_time:
                latest_time = meta["captured_time"]
                latest_region = meta["region_name"]

    return {
        "index": index, "assets": assets,
        "latest_time": latest_time, "latest_region": latest_region, "error": None,
    }


@st.cache_data(ttl=300, show_spinner=False)
def _load_display_image(key: str) -> Optional[np.ndarray]:
    """S3 객체를 (로컬 캐시를 거쳐) 화면에 표시할 RGB 배열로 읽어온다. 실패하면 None.

    SAR 원본 TIF는 브라우저가 표시하지 못하므로 밝기 정규화를 거쳐 RGB로 바꾼다.
    """
    local = s3_store.ensure_local(key)
    if local is None:
        return None
    try:
        img = Image.open(local)
        if local.suffix.lower() in (".tif", ".tiff"):
            return normalize_to_uint8_rgb(np.array(img))
        return np.array(img.convert("RGB"))
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _report_image_b64(key: str) -> Optional[str]:
    """보고서(HTML)에 내장할 JPEG base64 문자열을 만든다 (최대 640px로 축소). 실패하면 None."""
    image = _load_display_image(key)
    if image is None:
        return None
    img = Image.fromarray(image).convert("RGB")
    img.thumbnail((640, 640))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode()


# =====================================================================
# 2) 헤더와 상단 컨트롤 — 지역 + 촬영 시각(연/월/일/시) 선택
# =====================================================================

def _render_header() -> None:
    """로고와 제목·설명을 페이지 상단에 그린다 (한 화면 배치를 위해 낮게 유지)."""
    logo_path = _LOGO_SMALL_PATH if _LOGO_SMALL_PATH.exists() else _LOGO_PATH
    if logo_path.exists():
        logo_col, title_col = st.columns([0.06, 0.94], vertical_alignment="center")
        with logo_col:
            st.image(str(logo_path), use_container_width=True)
        with title_col:
            render_command_bar("EO/SAR 비교 분석")
    else:
        render_command_bar("EO/SAR 비교 분석")


def _render_controls(catalog: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """지역·연·월·일·시 선택 컨트롤을 그리고 선택값을 돌려준다 (날짜가 무효하면 None)."""
    latest: Optional[datetime] = catalog["latest_time"]
    default_region = catalog["latest_region"] if catalog["latest_region"] in _REGIONS else _REGIONS[0]
    default_time = latest or datetime.now()

    # 연도 선택지는 실제 사진이 있는 연도들 (없으면 올해만).
    years = sorted({
        datetime.fromisoformat(k[1]).year
        for k in catalog["index"]
    }) or [datetime.now().year]

    region_col, year_col, month_col, day_col, hour_col = st.columns(
        [1.4, 1.0, 0.8, 0.8, 0.8],
        vertical_alignment="bottom",
    )
    with region_col:
        region = st.selectbox("지역 선택", _REGIONS, index=_REGIONS.index(default_region))
    with year_col:
        year = st.selectbox(
            "연",
            years,
            index=years.index(default_time.year) if default_time.year in years else 0,
            format_func=lambda y: f"{y}년",
        )
    with month_col:
        month = st.selectbox(
            "월",
            list(range(1, 13)),
            index=default_time.month - 1,
            format_func=lambda m: f"{m}월",
        )
    with day_col:
        day = st.selectbox(
            "일",
            list(range(1, 32)),
            index=default_time.day - 1,
            format_func=lambda d: f"{d}일",
        )
    with hour_col:
        default_hour = default_time.hour if default_time.hour in _HOURS else _HOURS[0]
        hour = st.selectbox(
            "시",
            _HOURS,
            index=_HOURS.index(default_hour),
            format_func=lambda h: f"{h:02d}시",
        )

    try:
        selected = datetime(year, month, day, hour)
    except ValueError:
        st.warning("존재하지 않는 날짜입니다 (예: 2월 30일). 일자를 다시 선택하세요.")
        return None

    return {"region": region, "captured_time": selected}


# =====================================================================
# 3) 비교 그리드 — EO 행(원본|분석)을 위에, SAR 행(원본|분석)을 아래에
# =====================================================================

def _collect_cells(catalog: Dict[str, Any], region: str, captured_time: datetime) -> List[Dict[str, Any]]:
    """선택한 지역·시각의 4개 패널(EO/SAR × 원본/분석) 정보를 만든다 (화면·보고서 공용)."""
    index = catalog["index"]
    time_key = captured_time.isoformat()
    cells = []
    for sensor in ("EO", "SAR"):
        for kind, kind_title in (("original", "원본"), ("result", "분석 이미지")):
            cells.append(
                {
                    "sensor": sensor,
                    "kind": kind,
                    "title": f"{sensor} {kind_title}",
                    "key": index.get((region, time_key, sensor, kind)),
                    "memo_key": f"compare_memo_{sensor}_{kind}",
                }
            )
    return cells


def _render_image_cell(cell: Dict[str, Any]) -> None:
    """비교 그리드의 칸 하나: 제목 → [이미지 | 메모]를 좌우로 배치해 세로 길이를 줄인다."""
    key = cell["key"]
    with bracket_panel(f"eosar_compare_{cell['memo_key']}"):
        st.markdown(f"**{cell['title']}**")
        image_col, memo_col = st.columns([1.5, 1.0], gap="small")

        with image_col:
            image = _load_display_image(key) if key else None
            if key is not None and image is not None:
                st.image(image, use_container_width=True)
            else:
                if _LOGO_PATH.exists():
                    _, middle, _ = st.columns([1, 2, 1])
                    with middle:
                        st.image(str(_LOGO_PATH), use_container_width=True)
                if key is None:
                    st.caption("선택한 지역·시각에 해당하는 이미지가 없습니다.")
                else:
                    st.caption(f"이미지를 불러오지 못했습니다: {key}")

        with memo_col:
            st.text_area(
                "메모",
                key=cell["memo_key"],
                max_chars=500,
                placeholder="메모를 입력하세요.",
                height=160,
            )
            if key:
                st.caption(f"파일: {key.split('/', 1)[-1]}")

def _render_compare_grid(cells: List[Dict[str, Any]]) -> None:
    """4개 패널을 EO 행(위)·SAR 행(아래) 2×2로 그린다."""
    for row_start in (0, 2):   # cells[0:2]=EO(원본|분석), cells[2:4]=SAR(원본|분석)
        left, right = st.columns(2, gap="small")
        with left:
            _render_image_cell(cells[row_start])
        with right:
            _render_image_cell(cells[row_start + 1])


# =====================================================================
# 4) HTML 보고서 — 자가완결형(이미지 내장) 비교 분석 보고서를 만든다
# =====================================================================

def _report_panel_html(cell: Dict[str, Any], memo: str) -> str:
    """보고서의 패널 하나(제목 + 이미지 또는 '영상 없음' + 메모)를 HTML로 만든다."""
    title = html_lib.escape(cell["title"])
    key = cell["key"]

    if key:
        b64 = _report_image_b64(key)
        filename = html_lib.escape(key.split("/", 1)[-1])
        if b64:
            body = (
                f'<img class="shot" src="data:image/jpeg;base64,{b64}" alt="{title}">'
                f'<div class="file">파일: {filename}</div>'
            )
        else:
            body = f'<div class="missing">이미지를 불러오지 못했습니다<br>({filename})</div>'
    else:
        body = '<div class="missing">해당 시각의 영상 없음</div>'

    memo_html = html_lib.escape(memo).replace("\n", "<br>") if memo.strip() else "<i>메모 없음</i>"
    return (
        f'<div class="panel">'
        f'<div class="panel-title">{title}</div>'
        f'{body}'
        f'<div class="memo"><b>판독 메모</b><br>{memo_html}</div>'
        f'</div>'
    )


def _build_report_html(
    region: str,
    asset_name: str,
    captured_time: datetime,
    cells: List[Dict[str, Any]],
    memos: Dict[str, str],
) -> str:
    """비교 분석 결과 전체를 하나의 자가완결형 HTML 문서로 조립한다."""
    generated_at = datetime.now()

    # 영상 보유 현황 표 (없는 센서/종류도 한눈에 보이게).
    status_cells = "".join(
        f"<td class=\"{'ok' if cell['key'] else 'no'}\">{'보유' if cell['key'] else '없음'}</td>"
        for cell in cells
    )

    # 패널: EO 행(원본|분석) 위, SAR 행(원본|분석) 아래 — 화면과 같은 배치.
    eo_row = "".join(_report_panel_html(c, memos.get(c["memo_key"], "")) for c in cells[0:2])
    sar_row = "".join(_report_panel_html(c, memos.get(c["memo_key"], "")) for c in cells[2:4])

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>EO/SAR 비교 분석 보고서 — {html_lib.escape(region)} {captured_time:%Y-%m-%d %H시}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    max-width: 800px;
    margin: 40px auto;
    padding: 0 12px;
    line-height: 1.6;
    color: #1a1a1a;
    background: #fff;
  }}
  h1 {{ margin: 0 0 24px; font-size: 20px; text-align: center; }}
  h2 {{ margin: 26px 0 8px; font-size: 16px; }}
  .meta-list {{ margin-bottom: 20px; }}
  .meta-list p {{ margin: 3px 0; font-size: 14px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; font-size: 13px; text-align: center; }}
  th {{ background: #f2f2f2; font-weight: 700; }}
  td.ok, td.no {{ font-weight: 700; }}
  .row {{ display: flex; gap: 12px; align-items: stretch; }}
  .panel {{ flex: 1 1 0; min-width: 0; border: 1px solid #ccc; padding: 9px; }}
  .panel-title {{ font-weight: 700; font-size: 13px; margin-bottom: 7px; }}
  img.shot {{
    display: block;
    width: auto;
    max-width: 100%;
    height: 210px;
    margin: 0 auto;
    object-fit: contain;
  }}
  .file {{ margin-top: 5px; color: #666; font-size: 10px; word-break: break-all; }}
  .missing {{
    height: 210px;
    border: 1px dashed #bbb;
    color: #666;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 12px;
    text-align: center;
    font-size: 12px;
  }}
  .memo {{
    min-height: 54px;
    margin-top: 8px;
    padding-top: 7px;
    border-top: 1px solid #ddd;
    font-size: 12px;
  }}
  .foot {{ margin-top: 24px; color: #666; font-size: 11px; text-align: right; }}
  @media print {{
    body {{ margin: 16mm auto; padding: 0; }}
    .row, .panel {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
  <h1>EO/SAR 비교 분석 보고서</h1>

  <div class="meta-list">
    <p>1. 작성시각: {generated_at:%Y-%m-%d %H:%M:%S}</p>
    <p>2. 촬영자산: {html_lib.escape(asset_name or '-')}</p>
    <p>3. 지역명: {html_lib.escape(region)}</p>
    <p>4. 촬영시각: {captured_time:%Y-%m-%d %H:%M}</p>
  </div>

  <h2>영상 보유 현황</h2>
  <table>
    <tr>
      <th>EO 원본</th><th>EO 분석</th><th>SAR 원본</th><th>SAR 분석</th>
    </tr>
    <tr>
      {status_cells}
    </tr>
  </table>

  <h2>EO (전자광학)</h2>
  <div class="row">{eo_row}</div>

  <h2>SAR (합성개구레이더)</h2>
  <div class="row">{sar_row}</div>

  <div class="foot">ARGOS EO/SAR 비교 분석 · {generated_at:%Y-%m-%d %H:%M:%S}</div>
</body>
</html>"""


# =====================================================================
# 5) 페이지 진입점
# =====================================================================

def render_eosar_compare_page() -> None:
    """EO/SAR 비교 분석 페이지 전체를 그린다: 지역·시각 선택 → 2×2 비교 그리드 → 보고서 저장."""
    _render_header()

    catalog = _load_catalog()
    if catalog["error"]:
        st.error(f"S3 이미지 목록 조회 실패: {catalog['error']}")
        st.stop()
    if not catalog["index"]:
        st.warning("S3(original_image/·result_image/)에 비교할 이미지가 없습니다.")
        st.stop()

    with bracket_panel("eosar_compare_controls_panel"):
        controls_area, button_area = st.columns([4.8, 1.2], vertical_alignment="bottom")
        with controls_area:
            selection = _render_controls(catalog)

    if selection is None:
        return

    region = selection["region"]
    captured_time = selection["captured_time"]
    cells = _collect_cells(catalog, region, captured_time)

    # 오른쪽 위 버튼: 현재 선택·메모를 반영한 HTML 보고서 다운로드.
    memos = {cell["memo_key"]: str(st.session_state.get(cell["memo_key"], "")) for cell in cells}
    report_html = _build_report_html(
        region,
        catalog["assets"].get(region, ""),
        captured_time,
        cells,
        memos,
    )
    with button_area:
        st.download_button(
            "HTML 보고서 저장",
            data=report_html.encode("utf-8"),
            file_name=f"EOSAR_비교보고서_{region}_{captured_time:%Y%m%d_%H%M}.html",
            mime="text/html",
            type="primary",
            use_container_width=True,
        )

    _render_compare_grid(cells)
