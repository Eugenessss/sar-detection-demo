import datetime

import altair as alt
import streamlit as st
from streamlit_folium import st_folium

from features.ANALYST_DESK import service
from features.statistics import service as stats_service
from shared.ui_chrome import bracket_panel, render_command_bar

# 마커 클릭으로 어느 경보 좌표를 눌렀는지 판별할 때 쓰는 오차 허용치(도 단위, 약 100m).
_CLICK_MATCH_TOLERANCE = 0.001


def _find_alert_by_click(lat: float, lng: float, alerts: list) -> "service.Alert | None":
    """지도에서 클릭된 좌표와 가장 가까운(오차범위 내) 경보를 찾는다."""
    for alert in alerts:
        if abs(alert.latitude - lat) <= _CLICK_MATCH_TOLERANCE and \
           abs(alert.longitude - lng) <= _CLICK_MATCH_TOLERANCE:
            return alert
    return None


def _render_map_column() -> None:
    """왼쪽 칸: 한반도 위성사진 + 경보 마커 지도. 마커를 누르면 EO/SAR 판독 페이지로 바로 이동한다."""
    # 센서 필터: 경보는 센서(EO/SAR)별 독립 체인으로 생성되므로, "전체"에서는
    # 지역별 최신 1건에 다른 센서의 경보가 가려질 수 있다. 센서를 고르면
    # 그 센서의 경보만 대상으로 지역별 최신 1건씩 표시한다.
    sensor_choice = st.segmented_control(
        "센서", ["전체", "EO", "SAR"], key="analyst_desk_sensor_filter", default="전체",
    )
    sensor = None if sensor_choice in (None, "전체") else sensor_choice

    try:
        m = service.build_eo_map()
    except Exception as exc:
        st.error(f"위성 지도 생성 실패: {exc}")
        return

    # 경보(alert_id) 목록을 DB에서 조회해 지도에 마커로 표시.
    # 색은 경보수준(긴급/중요/특이)에 따라 다르게 찍는다.
    try:
        alerts = service.get_alerts(sensor)
    except Exception as exc:
        st.error(f"경보 조회 실패: {exc}")
        alerts = []

    if not alerts and sensor:
        st.info(f"{sensor} 경보가 없습니다.")

    for alert in alerts:
        level_label = service.marker_label(alert.alert_level)
        marker_color = service.marker_color(alert.alert_level)
        if alert.alert_level == "URGENT":
            service.add_threat_rings(m, alert.latitude, alert.longitude, marker_color)
        service.add_circle_marker(
            m, alert.latitude, alert.longitude,
            color=marker_color,
            tooltip=f"[{level_label}·{alert.sensor_type}] {alert.asset_name}",
        )

    st.caption("마커 색상: 🔴 긴급 · 🟠 중요 · 🔵 특이 (마커를 누르면 EO/SAR 판독 페이지로 이동)")

    # 센서 필터를 key에 넣는다 — 필터를 바꾸면 지도를 새로 만들어, 직전 필터에서
    # 클릭했던 좌표가 남아 엉뚱한 경보로 넘어가는 것을 막는다.
    # 리셋 토큰도 넣는다 — EO/SAR로 이동했다가 상단 메뉴로 이 페이지에 돌아왔을 때
    # 같은 key를 계속 쓰면 이전 클릭 좌표를 그대로 기억하고 있어서, 돌아오자마자
    # 다시 클릭한 것처럼 인식해 또 이동해버리는 문제가 있다. 마커를 눌러 이동하기
    # 직전에 토큰을 올려두면(아래) 돌아왔을 때 지도 컴포넌트가 새로 만들어진다.
    map_key = f"analyst-desk-alert-map-{st.session_state.get('_analyst_desk_map_reset_token', 0)}-{sensor_choice}"
    map_data = st_folium(
        m, height=650,
        use_container_width=True,
        returned_objects=["last_object_clicked"],
        key=map_key,
    )

    clicked = map_data.get("last_object_clicked") if map_data else None
    if clicked:
        matched = _find_alert_by_click(clicked["lat"], clicked["lng"], alerts)
        if matched is not None:
            st.session_state["_analyst_desk_map_reset_token"] = (
                st.session_state.get("_analyst_desk_map_reset_token", 0) + 1
            )
            eosar_page = st.session_state.get("_pages_by_url", {}).get("eosar")
            if eosar_page is None:
                st.error("EO/SAR 페이지를 찾을 수 없습니다.")
            else:
                st.switch_page(eosar_page)


def _render_24h_chart(overlay_data) -> None:
    """실제(실선)/2시간 평균(점선) 겹쳐그리기 그래프 (statistics 페이지의 24시간 그래프와 같은 형태)."""
    if overlay_data.empty:
        st.info("최근 24시간 동안 표시할 통계가 없습니다.")
        return
    chart = (
        alt.Chart(overlay_data)
        .mark_line()
        .encode(
            x=alt.X("captured_time:T", title="촬영시각"),
            y=alt.Y("detected_count:Q", title="탐지 수"),
            color=alt.Color("class_name:N", title="장비"),
            strokeDash=alt.StrokeDash("series:N", title="구분 (실제/평균)"),
            tooltip=["class_name", "series", "captured_time:T", "detected_count:Q"],
        )
        .properties(height=610)
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True)


_STATS_REGION_KEY = "analyst_desk_stats_region"


def _render_region_control() -> str:
    """그래프 위: 지역 선택 팝오버 하나만 두고, 그 안에 지역 이름을 버튼으로 나열한다.
    선택된 region_name을 돌려준다 ("전체"면 필터 없음)."""
    try:
        regions = stats_service.list_regions()
    except Exception as exc:
        st.error(f"지역 목록 조회 실패: {exc}")
        regions = []

    if _STATS_REGION_KEY not in st.session_state:
        st.session_state[_STATS_REGION_KEY] = "전체"

    with st.popover(f"장소 선택 ({st.session_state[_STATS_REGION_KEY]})", use_container_width=True):
        for region_name in ["전체"] + regions:
            if st.button(region_name, use_container_width=True, key=f"analyst_desk_region_{region_name}"):
                st.session_state[_STATS_REGION_KEY] = region_name

    return st.session_state[_STATS_REGION_KEY]


def _render_statistics_detail_button() -> None:
    """그래프 아래: statistics 페이지(장소·장비·기간을 자유롭게 조회하는 전체 통계 화면)로 이동하는 버튼."""
    if st.button("상세 통계", use_container_width=True, key="analyst_desk_go_statistics"):
        statistics_page = st.session_state.get("_pages_by_url", {}).get("statistics")
        if statistics_page is None:
            st.error("Statistics 페이지를 찾을 수 없습니다.")
        else:
            st.switch_page(statistics_page)


def _render_statistics_column() -> None:
    """오른쪽 칸: 지역 선택(팝오버) 하나만 두고, 조회 시점(현재 시각) 기준 최근 24시간
    탐지 통계 그래프를 보여준 뒤, 그 아래에 상세 통계 페이지로 이동하는 버튼을 둔다."""
    st.subheader("최근 24시간 탐지 통계")

    region = _render_region_control()

    now = datetime.datetime.now()
    start, end = stats_service.resolve_range(now - datetime.timedelta(hours=24), "24시간")
    st.caption(f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}")

    result = None
    query_failed = False
    with st.spinner("통계 조회 중..."):
        try:
            result = stats_service.build_statistics(start, end)
        except Exception as exc:
            st.error(f"통계 조회 실패: {exc}")
            query_failed = True

    if not query_failed:
        if result is None:
            st.warning("최근 24시간 동안 조회된 탐지 결과가 없습니다.")
        else:
            selected_region = None if region == "전체" else region
            overlay_data = stats_service.build_two_hour_overlay(result.raw, start, end, selected_region)
            _render_24h_chart(overlay_data)

    _render_statistics_detail_button()


def render_map_view() -> None:
    """왼쪽엔 경보 지도, 오른쪽엔 최근 24시간 탐지 통계 그래프를 나란히 보여준다."""
    render_command_bar("영상판독관 페이지")

    map_col, stats_col = st.columns([1, 1], gap="large")

    with map_col:
        with bracket_panel("analyst_map_panel"):
            _render_map_column()

    with stats_col:
        with bracket_panel("analyst_stats_panel"):
            _render_statistics_column()


def render_hq_desk_page() -> None:
    """Analyst Desk 페이지 진입점. 지도 + 최근 24시간 통계를 보여준다."""
    render_map_view()
