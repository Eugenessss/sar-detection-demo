"""
[경보 상세 화면]
지도(view.py)에서 마커를 클릭했을 때 보여주는 상세 페이지.
상단 메뉴에는 노출하지 않고 view.py 안에서 세션 상태(view/selected_alert_id)로만 전환한다.

전체를 3:4:3 비율의 3칸으로 나눈다.
  왼쪽(3)   : 적군 자산 정보 카드. 경보수준·제목·변화요약·지역 + 탐지된 적군
              장비(equipment 테이블: 종류·위협도·설명) - 전부 DB 조회 결과.
  가운데(4) : 위성사진. 사진은 (크기가 제각각이라) 잘라내거나 늘리지 않고 원본
              비율 그대로 화면 폭에 맞춰 보여준다. [H-4]/[H-2]/[H-Hour] 버튼으로
              시간을 고르고, 오른쪽에서 사거리를 만족해 체크한 무장 옵션이 있으면
              사진 위에 그 무장의 타격반경(effect_radius_m) 크기 원이 겹쳐 그려진다
              (1픽셀 = 1미터로 계산).
  오른쪽(3) : 아군 자산 지도 (경보 지도와 같은 EO 배경 + 부대 단위 마커) + 그 아래
              마커를 클릭하면 나오는, 그 부대가 쓸 수 있는 무장 옵션 체크리스트.
              아군 자산은 ally_asset 테이블(부대+장비+무장 조합)에서 조회하고,
              alert의 적군 좌표까지 거리를 계산해 사거리(range_km)를 만족하는
              옵션만 체크(선택) 가능하다.
"""
import base64
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from PIL import Image
from streamlit_folium import st_folium

from features.HQ_DESK import service


def _render_enemy_asset_card(alert: service.Alert) -> None:
    """왼쪽(3): 경보정보(레벨·제목·변화요약·지역) + 탐지된 적군 자산 정보를 세로로 보여준다."""
    level_label = service.marker_label(alert.alert_level)
    st.markdown(
        "  \n".join([
            f":{service.marker_color(alert.alert_level)}[**[{level_label}]**]",
            f"**{alert.title or '(제목 없음)'}**",
        ])
    )

    st.caption("변화 요약")
    st.write(alert.summary or "변화 요약 정보가 없습니다.")

    st.caption("지역")
    st.write(alert.region or "지역 정보가 없습니다.")

    st.markdown("<hr style='margin:4px 0 10px 0;' />", unsafe_allow_html=True)

    st.markdown("**적군 자산 정보**")
    asset_lines = [f"장비: {alert.asset_name or '정보 없음'}"]
    if alert.asset_category:
        asset_lines.append(f"종류: {alert.asset_category}")
    if alert.asset_threat_level is not None:
        asset_lines.append(f"위협도: {alert.asset_threat_level}")
    st.markdown("  \n".join(asset_lines))
    if alert.asset_description:
        st.caption(alert.asset_description)


def _image_data_uri(path: Path) -> str:
    """이미지 파일을 <img> 태그에 바로 쓸 수 있는 base64 data URI로 바꾼다."""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


# 오른쪽 아군 자산 지도(st_folium) 높이 기준값. 사진은 이제 원본 비율로 그리므로
# (사진마다 크기가 다를 수 있어) 항상 이 높이와 정확히 일치하진 않을 수 있다.
_PHOTO_MAP_HEIGHT_PX = 480

# "일단 1픽셀당 1m"로 그린다는 요청에 따른 고정 환산 비율. 실제 GSD(지상표본거리)가
# 확인되면 이 값만 바꾸면 된다.
_METERS_PER_PIXEL = 1.0

# 원이 여러 개 겹쳐도 구분되도록 옵션마다 돌아가며 쓰는 색상.
_CIRCLE_COLORS = ["#FF4B4B", "#FFA940", "#00BFFF", "#7CFC00", "#DA70D6", "#FFD700"]


def _get_image_size(path: Path) -> Tuple[int, int]:
    """이미지 파일의 원본 (가로, 세로) 픽셀 크기를 읽는다."""
    with Image.open(path) as img:
        return img.size


def _circle_count_for(asset: service.AllyAsset) -> int:
    """무장 종류에 따라 그릴 원의 개수를 정한다 (요청사항 기준, 그 외는 중앙 1개)."""
    if asset.munition_name == "집속탄":
        return 200
    if asset.munition_name == "130mm 무유도미사일":
        return 12
    if asset.category == "자주곡사포":
        return 6
    return 1


def _circle_centers(
    asset: service.AllyAsset, width_px: int, height_px: int, count: int, seed: Any,
) -> List[Tuple[float, float]]:
    """count가 1이면 사진 정중앙, 그 이상이면 사진 안쪽 무작위 위치 목록을 만든다.

    seed를 고정해서, 같은 경보·같은 자산이면 다시 그릴 때도 같은 배치가 나오도록 한다
    (매 rerun마다 점이 흔들리며 다시 찍히는 걸 방지).
    """
    if count <= 1:
        return [(width_px / 2.0, height_px / 2.0)]

    radius_px = (asset.effect_radius_m or 0.0) * _METERS_PER_PIXEL
    rng = random.Random(seed)
    margin_x = min(radius_px, width_px / 2.0)
    margin_y = min(radius_px, height_px / 2.0)

    centers: List[Tuple[float, float]] = []
    for _ in range(count):
        cx = rng.uniform(margin_x, width_px - margin_x) if width_px > 2 * margin_x else width_px / 2.0
        cy = rng.uniform(margin_y, height_px - margin_y) if height_px > 2 * margin_y else height_px / 2.0
        centers.append((cx, cy))
    return centers


def _render_image_slot(
    path: Optional[Path],
    circles: Optional[List[Tuple[int, service.AllyAsset]]] = None,
) -> None:
    """이미지를 원본 비율 그대로(잘리거나 늘어나지 않게) 화면 폭에 맞춰 보여준다.

    circles는 (alert_id, asset) 목록. asset마다 무장 종류에 따라 정해진 개수
    (기본 1개 · 집속탄 200개 · 자주곡사포 6개 · 130mm 무유도미사일 12개)만큼
    effect_radius_m 크기의 원을 사진 위에 겹쳐 그린다 (1픽셀 = 1미터로 계산).

    사진이 제각각 크기라, 원의 위치·크기를 원본 픽셀 좌표의 '비율(%)'로 계산해서
    사진이 화면 폭에 맞춰 확대/축소되어도 원이 항상 같은 상대 위치·비율로 따라오게 한다.
    래퍼 div에 aspect-ratio를 원본과 똑같이 지정해 두면, 축소돼도 잘림·여백 없이
    사진과 원이 함께 정확한 비율로 줄어든다.
    """
    if path is None or not path.exists():
        st.info("이미지가 없습니다. (준비 중)")
        return

    width_px, height_px = _get_image_size(path)

    overlay_divs: List[str] = []
    legend_items: List[str] = []
    for idx, (alert_id, asset) in enumerate(circles or []):
        color = _CIRCLE_COLORS[idx % len(_CIRCLE_COLORS)]
        label = f"{asset.platform_name}·{asset.munition_name}"

        if asset.effect_radius_m is None:
            legend_items.append(f'<span style="color:{color};">●</span> {label} (타격반경 정보 없음)')
            continue

        count = _circle_count_for(asset)
        centers = _circle_centers(asset, width_px, height_px, count, seed=(alert_id, asset.asset_id))
        diameter_px = max(1.0, asset.effect_radius_m * _METERS_PER_PIXEL * 2)
        d_pct_w = diameter_px / width_px * 100
        d_pct_h = diameter_px / height_px * 100

        for cx, cy in centers:
            left_pct = cx / width_px * 100
            top_pct = cy / height_px * 100
            overlay_divs.append(
                f'<div style="position:absolute;top:{top_pct:.3f}%;left:{left_pct:.3f}%;'
                f'width:{d_pct_w:.3f}%;height:{d_pct_h:.3f}%;'
                f'transform:translate(-50%,-50%);border-radius:50%;'
                f'border:1.5px solid {color};background:{color}33;'
                f'pointer-events:none;box-sizing:border-box;"></div>'
            )

        count_note = f" × {count}" if count > 1 else ""
        legend_items.append(f'<span style="color:{color};">●</span> {label} ({asset.effect_radius_m:.0f}m{count_note})')

    st.markdown(
        f'<div style="position:relative;width:100%;aspect-ratio:{width_px}/{height_px};line-height:0;">'
        f'<img src="{_image_data_uri(path)}" '
        f'style="width:100%;height:100%;display:block;border-radius:4px;object-fit:contain;" />'
        f'{"".join(overlay_divs)}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if legend_items:
        st.markdown(
            f'<div style="font-size:0.8rem;margin-top:4px;">{" &nbsp;·&nbsp; ".join(legend_items)}</div>',
            unsafe_allow_html=True,
        )


# @st.fragment로 감싸서, 시간 버튼을 눌렀을 때 이 사진 영역만 다시 그리고
# 오른쪽 아군 자산 지도(전체 rerun 시 다시 로딩되던 부분)는 건드리지 않게 한다.
@st.fragment
def _render_alert_photos(alert_id: int, circles: List[service.AllyAsset]) -> None:
    """[H-4]/[H-2]/[H-Hour] 중에서 고른 사진 한 장을 보여주고, 선택된 무장 옵션의
    타격반경 원을 그 위에 겹쳐 그린다."""
    images = service.get_alert_images(alert_id)
    labels = ["[H-4]", "[H-2]", "[H-Hour]"]
    # images는 오래된 순 최대 3장. 가장 최신 장이 경보 기준 시각(H-Hour)이므로
    # 라벨 뒤쪽부터 맞춘다 — 3장 미만이면 비는 쪽은 과거 슬롯(H-4 방향)이어야 한다.
    offset = len(labels) - len(images)

    state_key = f"photo_time_label_{alert_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = labels[-1]  # 기본 선택은 경보 기준 사진(H-Hour)

    # segmented_control은 선택 상태를 위젯 자체가 직접 관리해서, 버튼 방식처럼
    # "한 번 눌러야 상태만 바뀌고 색은 다음 클릭에야 반영되는" 딜레이가 없다.
    selected_label = st.segmented_control(
        "촬영 시각", labels, key=state_key,
    )
    selected_idx = labels.index(selected_label) if selected_label in labels else len(labels) - 1

    image_idx = selected_idx - offset
    image_path = images[image_idx] if 0 <= image_idx < len(images) else None
    circle_pairs = [(alert_id, asset) for asset in circles]
    _render_image_slot(image_path, circles=circle_pairs)


def _find_unit_by_click(lat: float, lng: float, units: List[Dict[str, Any]], tolerance: float = 0.001) -> Optional[Dict[str, Any]]:
    """지도에서 클릭한 좌표와 가장 가까운(오차범위 내) 아군 부대를 찾는다."""
    for unit in units:
        if abs(unit["latitude"] - lat) <= tolerance and abs(unit["longitude"] - lng) <= tolerance:
            return unit
    return None


def _render_friendly_asset_panel(
    alert: service.Alert,
    evaluated_assets: List[service.AllyAsset],
    selection_key: str,
) -> None:
    """오른쪽: 아군 자산 지도(부대 단위 마커) + 마커 클릭 시 그 부대의 무장 옵션 체크리스트.

    체크리스트는 사거리(range_km)가 적군까지 거리(distance_km)를 만족하는 옵션만
    선택(체크) 가능하고, 체크 상태는 st.session_state[selection_key](asset_id 집합)에
    저장된다. (사진에 바로 반영되도록 이 값은 render_alert_detail_page 맨 앞에서
    한 번 더 동기화한다 — 아래 render_alert_detail_page의 주석 참고.)
    """
    st.caption("아군 자산 위치")
    # 왼쪽 사진 컬럼은 "촬영 시각" 라벨 + 시간 선택 버튼줄이 캡션 위에 하나 더 있어서,
    # 지도가 캡션 바로 아래에서 시작하면 사진 박스보다 위쪽 끝이 더 높아 보인다.
    # 버튼줄 높이만큼 빈 여백을 넣어서 사진 박스와 지도 박스의 위쪽 끝을 맞춘다.
    st.markdown("<div style='height:44px;'></div>", unsafe_allow_html=True)

    try:
        friendly_map = service.build_eo_map()
    except Exception as exc:
        st.error(f"아군 자산 지도 생성 실패: {exc}")
        return

    units = service.group_ally_units(evaluated_assets)
    for unit in units:
        service.add_circle_marker(
            friendly_map, unit["latitude"], unit["longitude"],
            color=service.FRIENDLY_MARKER_COLOR,
            tooltip=f"{unit['unit_name']} ({unit['platform_name']})",
        )

    # 왼쪽 사진 박스와 높이를 똑같이 맞춰서 아래쪽 끝도 나란히 정렬한다.
    map_key = f"friendly-map-{st.session_state.get('_map_reset_token', 0)}"
    map_data = st_folium(
        friendly_map, height=_PHOTO_MAP_HEIGHT_PX,
        use_container_width=True,
        returned_objects=["last_object_clicked"],
        key=map_key,
    )

    clicked = map_data.get("last_object_clicked") if map_data else None
    if clicked:
        matched_unit = _find_unit_by_click(clicked["lat"], clicked["lng"], units)
        if matched_unit is not None:
            st.session_state["hq_selected_unit"] = matched_unit["unit_name"]

    selected_unit_name = st.session_state.get("hq_selected_unit")
    st.markdown("**타격 옵션 선택** (사거리를 만족하는 무장만 체크 가능)")

    if selected_unit_name is None:
        st.info("마커를 누르면 그 부대가 쓸 수 있는 무장 옵션이 표시됩니다.")
        return

    options = [a for a in evaluated_assets if a.unit_name == selected_unit_name]
    if not options:
        st.warning(f"{selected_unit_name}의 무장 옵션을 찾을 수 없습니다.")
        return

    selected_ids = st.session_state.setdefault(selection_key, set())
    st.caption(f"선택 부대: {selected_unit_name}")

    for asset in options:
        label = (
            f"{asset.platform_name} · {asset.munition_name}  "
            f"(거리 {asset.distance_km:.1f}km / 사거리 {asset.range_km:.0f}km"
            f"{' · 충족' if asset.in_range else ' · 사거리 밖'})"
        )
        widget_key = f"hq_munition_{alert.alert_id}_{asset.asset_id}"
        if asset.in_range:
            checked = st.checkbox(label, value=asset.asset_id in selected_ids, key=widget_key)
            if checked:
                selected_ids.add(asset.asset_id)
            else:
                selected_ids.discard(asset.asset_id)
        else:
            st.checkbox(label, value=False, disabled=True, key=widget_key)


def _sync_selected_munitions(
    alert: service.Alert, evaluated_assets: List[service.AllyAsset], selection_key: str,
) -> None:
    """체크박스를 실제로 그리기 전에, 이미 세션에 반영된 위젯 클릭 결과를 selection
    set에 먼저 반영한다.

    문제였던 상황: 컬럼 순서상 가운데(사진)가 오른쪽(체크박스)보다 먼저 그려지는데,
    체크박스를 클릭한 직후의 rerun에서 selection set 갱신이 체크박스 렌더링 코드
    안(오른쪽 패널)에서만 일어나면, 이미 그 앞에서 그려진 사진은 "클릭 전" 상태를
    보여주게 된다 (한 박자 늦게 반영되는 버그). Streamlit은 위젯에 key를 주면 클릭
    직후 rerun 시작 시점에 이미 st.session_state[key]를 새 값으로 갱신해두므로,
    위젯을 굳이 다시 그리지 않아도 이 값을 미리 읽어 selection set에 반영할 수 있다.
    그래서 사진을 그리기 전, 여기서 한 번 더 동기화한다.
    """
    selected_ids = st.session_state.setdefault(selection_key, set())
    selected_unit_name = st.session_state.get("hq_selected_unit")
    if selected_unit_name is None:
        return

    for asset in evaluated_assets:
        if asset.unit_name != selected_unit_name or not asset.in_range:
            continue
        widget_key = f"hq_munition_{alert.alert_id}_{asset.asset_id}"
        if widget_key not in st.session_state:
            continue
        if st.session_state[widget_key]:
            selected_ids.add(asset.asset_id)
        else:
            selected_ids.discard(asset.asset_id)


def render_alert_detail_page() -> None:
    """경보 상세 페이지 전체를 그린다."""
    # 페이지 상단 여백을 줄여서 전체 내용을 위로 올린다 (제목을 없앤 만큼 빈 공간이 남지 않도록).
    # 너무 줄이면 Streamlit 상단 툴바에 "지도로 돌아가기" 버튼이 가려져서 3rem으로 둔다.
    st.markdown("<style>div.block-container{padding-top:3rem;}</style>", unsafe_allow_html=True)

    if st.button("← 지도로 돌아가기"):
        st.session_state["view"] = "map"
        # 지도 컴포넌트를 새로 만들도록 key를 바꿔, 이전 클릭 좌표가 남아있지 않게 한다.
        st.session_state["_map_reset_token"] = st.session_state.get("_map_reset_token", 0) + 1
        st.rerun()

    alert_id = st.session_state.get("selected_alert_id")
    alert = None
    if alert_id is not None:
        try:
            alert = service.get_alert_by_id(alert_id)
        except Exception as exc:
            st.error(f"경보 조회 실패: {exc}")
            return

    if alert is None:
        st.warning("선택된 경보가 없습니다. 지도에서 마커를 눌러주세요.")
        return

    # 아군 자산(ally_asset) 조회 + 적군(alert의 region 좌표)까지 거리·사거리 충족 여부 계산.
    # 사진(가운데)에 그릴 원 목록을 먼저 정하기 위해, 컬럼을 나누기 전에 미리 계산한다.
    try:
        evaluated_assets = service.evaluate_ally_assets(
            service.get_ally_assets(), alert.latitude, alert.longitude,
        )
    except Exception as exc:
        st.error(f"아군 자산 조회 실패: {exc}")
        evaluated_assets = []

    # alert(경보)마다 선택 상태를 따로 기억해, 다른 경보를 보면 체크가 초기화되게 한다.
    selection_key = f"hq_selected_munitions_{alert.alert_id}"

    # 체크박스(오른쪽 패널)를 그리기 전에, 방금 클릭된 상태를 selection set에 먼저
    # 반영한다 — 그래야 이 아래에서 계산하는 selected_assets가 가운데 사진에 "바로" 반영된다.
    _sync_selected_munitions(alert, evaluated_assets, selection_key)

    selected_ids = st.session_state.get(selection_key, set())
    selected_assets = [a for a in evaluated_assets if a.asset_id in selected_ids]

    enemy_col, photo_col, friendly_col = st.columns([3, 4, 3])

    with enemy_col:
        _render_enemy_asset_card(alert)

    with photo_col:
        _render_alert_photos(alert.alert_id, selected_assets)

    with friendly_col:
        _render_friendly_asset_panel(alert, evaluated_assets, selection_key)
