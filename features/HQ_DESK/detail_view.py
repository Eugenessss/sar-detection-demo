"""
[경보 상세 화면]
지도(view.py)에서 마커를 클릭했을 때 보여주는 상세 페이지.
상단 메뉴에는 노출하지 않고 view.py 안에서 세션 상태(view/selected_alert_id)로만 전환한다.

전체를 3:4:3 비율의 3칸으로 나눈다.
  왼쪽(3)   : 적군 자산 정보 카드. 경보수준·제목·변화요약·지역 + 탐지된 적군
              장비(equipment 테이블: 종류·위협도·설명) - 전부 DB 조회 결과.
  가운데(4) : 위성사진. [H-4]/[H-2]/[H-Hour] 버튼으로 시간을 고르면 그 사진
              한 장이 (result_image/ 폴더, 촬영 시각순 정렬) 보이고, 오른쪽에서
              사거리를 만족해 체크한 무장 옵션이 있으면 사진 중앙에 타격반경
              (effect_radius_m) 크기의 원이 겹쳐 그려진다.
  오른쪽(3) : 아군 자산 지도 (경보 지도와 같은 EO 배경 + 부대 단위 마커) + 그 아래
              마커를 클릭하면 나오는, 그 부대가 쓸 수 있는 무장 옵션 체크리스트.
              아군 자산은 ally_asset 테이블(부대+장비+무장 조합)에서 조회하고,
              alert의 적군 좌표까지 거리를 계산해 사거리(range_km)를 만족하는
              옵션만 체크(선택) 가능하다.
"""
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
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


# 사진 박스와 오른쪽 지도(st_folium)의 높이를 똑같은 값으로 맞춰서, 두 박스의
# 위/아래 끝이 나란히 정렬되도록 한다 (오른쪽 지도의 height=도 이 값을 그대로 쓴다).
_PHOTO_MAP_HEIGHT_PX = 480

# 위성사진(원본 840x840 정사각형) 한 장이 실제로 촬영하는 것으로 "가정"하는 가로/세로
# 폭(m). effect_radius_m(실측 타격반경, m)을 사진 위 원의 픽셀 반지름으로 바꾸는 데 쓴다.
# (실제 GSD 값이 확인되면 이 값만 바꾸면 된다.)
_PHOTO_ASSUMED_FOOTPRINT_M = 1000.0
# 사진 박스를 840x840 원본과 같은 비율의 고정 정사각형(_PHOTO_MAP_HEIGHT_PX)으로 그리므로,
# 화면에 보이는 1m당 픽셀 수는 (표시 박스 크기 / 가정 촬영폭)으로 고정된다.
_PX_PER_METER = _PHOTO_MAP_HEIGHT_PX / _PHOTO_ASSUMED_FOOTPRINT_M  # 기본값: 0.48 px/m

# 원이 여러 개 겹쳐도 구분되도록 옵션마다 돌아가며 쓰는 색상.
_CIRCLE_COLORS = ["#FF4B4B", "#FFA940", "#00BFFF", "#7CFC00", "#DA70D6", "#FFD700"]


def _render_image_slot(
    path: Optional[Path],
    circles: Optional[List[service.AllyAsset]] = None,
    height_px: int = _PHOTO_MAP_HEIGHT_PX,
) -> None:
    """이미지 한 장을 고정 정사각형(height_px x height_px) 박스로 보여준다.

    circles로 넘어온 아군 자산(체크된 무장 옵션)마다, 사진 정중앙을 기준으로
    effect_radius_m을 반지름으로 하는 원을 겹쳐 그린다 (effect_radius_m이 없는
    옵션은 원 없이 범례에만 "타격반경 정보 없음"으로 표시).

    박스를 원본과 같은 정사각형 고정 크기로 그리는 이유: object-fit:cover를 폭
    100%(가변) 박스에 쓰면 브라우저 폭에 따라 잘리는 비율이 달라져서 원의 반지름을
    실제 미터 단위로 정확히 환산할 수 없기 때문. 정사각형↔정사각형은 잘림 없이
    균일하게 축소되므로 (표시크기/가정촬영폭)의 고정 배율(_PX_PER_METER)로 계산할 수 있다.
    """
    if path is None or not path.exists():
        st.info("이 시각의 이미지가 없습니다. (촬영분이 없거나, 다른 PC에서 저장되어 이 PC에 파일이 없는 경우)")
        return

    overlay_html = ""
    legend_items: List[str] = []
    for idx, asset in enumerate(circles or []):
        color = _CIRCLE_COLORS[idx % len(_CIRCLE_COLORS)]
        label = f"{asset.platform_name}·{asset.munition_name}"
        if asset.effect_radius_m is None:
            legend_items.append(f'<span style="color:{color};">●</span> {label} (타격반경 정보 없음)')
            continue

        diameter_px = max(6, round(asset.effect_radius_m * _PX_PER_METER * 2))
        overlay_html += (
            f'<div style="position:absolute;top:50%;left:50%;'
            f'width:{diameter_px}px;height:{diameter_px}px;'
            f'transform:translate(-50%,-50%);border-radius:50%;'
            f'border:2px solid {color};background:{color}33;'
            f'pointer-events:none;"></div>'
        )
        legend_items.append(f'<span style="color:{color};">●</span> {label} ({asset.effect_radius_m:.0f}m)')

    st.markdown(
        f'<div style="position:relative;width:{height_px}px;height:{height_px}px;margin:0 auto;'
        f'border-radius:4px;overflow:hidden;">'
        f'<img src="{_image_data_uri(path)}" '
        f'style="width:100%;height:100%;object-fit:cover;display:block;" />'
        f'{overlay_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if legend_items:
        st.markdown(
            f'<div style="text-align:center;font-size:0.8rem;margin-top:4px;">{" &nbsp;·&nbsp; ".join(legend_items)}</div>',
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
    _render_image_slot(image_path, circles=circles)


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
    저장되어 가운데 사진의 원 오버레이에 곧바로 반영된다.
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
    selected_ids = st.session_state.get(selection_key, set())
    selected_assets = [a for a in evaluated_assets if a.asset_id in selected_ids]

    enemy_col, photo_col, friendly_col = st.columns([3, 4, 3])

    with enemy_col:
        _render_enemy_asset_card(alert)

    with photo_col:
        _render_alert_photos(alert.alert_id, selected_assets)

    with friendly_col:
        _render_friendly_asset_panel(alert, evaluated_assets, selection_key)
