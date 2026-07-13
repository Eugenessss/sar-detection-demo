import streamlit as st
from streamlit_folium import st_folium

from features.HQ_DESK import detail_view, service

# 마커 클릭으로 어느 경보 좌표를 눌렀는지 판별할 때 쓰는 오차 허용치(도 단위, 약 100m).
_CLICK_MATCH_TOLERANCE = 0.001


def _find_alert_by_click(lat: float, lng: float, alerts: list) -> "service.Alert | None":
    """지도에서 클릭된 좌표와 가장 가까운(오차범위 내) 경보를 찾는다."""
    for alert in alerts:
        if abs(alert.latitude - lat) <= _CLICK_MATCH_TOLERANCE and \
           abs(alert.longitude - lng) <= _CLICK_MATCH_TOLERANCE:
            return alert
    return None


def render_map_view() -> None:
    """한반도 위성사진 + 경보 마커 지도를 그린다. 마커를 누르면 상세 화면으로 전환한다."""
    st.title("지휘관 페이지")

    # 센서 필터: 경보는 센서(EO/SAR)별 독립 체인으로 생성되므로, "전체"에서는
    # 지역별 최신 1건에 다른 센서의 경보가 가려질 수 있다. 센서를 고르면
    # 그 센서의 경보만 대상으로 지역별 최신 1건씩 표시한다.
    sensor_choice = st.segmented_control(
        "센서", ["전체", "EO", "SAR"], key="hq_sensor_filter", default="전체",
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
        service.add_circle_marker(
            m, alert.latitude, alert.longitude,
            color=service.marker_color(alert.alert_level),
            tooltip=f"[{level_label}·{alert.sensor_type}] {alert.asset_name}",
        )

    st.caption("마커 색상: 🔴 긴급 · 🟠 중요 · 🔵 특이 (마커를 누르면 상세 화면으로 이동)")

    # 상세 화면에서 돌아올 때마다 key를 바꿔 지도 컴포넌트를 새로 만든다.
    # (같은 key를 계속 쓰면 이전 클릭 좌표를 계속 기억하고 있어서, 같은 마커를
    #  다시 눌러도 "새 클릭"으로 인식하지 못하는 문제가 있었다.)
    # 센서 필터도 key에 넣는다 — 필터를 바꾸면 지도를 새로 만들어, 직전 필터에서
    # 클릭했던 좌표가 남아 엉뚱한 경보로 넘어가는 것을 막는다.
    map_key = f"alert-map-{st.session_state.get('_map_reset_token', 0)}-{sensor_choice}"
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
            st.session_state["selected_alert_id"] = matched.alert_id
            st.session_state["view"] = "detail"
            st.rerun()


def render_hq_desk_page() -> None:
    """HQ Desk 페이지 진입점. 기본은 지도, 마커 클릭 시 세션 상태로 상세 화면으로 전환한다."""
    if st.session_state.get("view") == "detail":
        detail_view.render_alert_detail_page()
    else:
        render_map_view()
