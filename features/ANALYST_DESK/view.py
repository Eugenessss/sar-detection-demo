import datetime

import altair as alt
import streamlit as st

from features.ANALYST_DESK import service
from features.statistics import service as stats_service
from shared import tactical_map
from shared.ui import MetricItem, render_metric_grid, render_page_header, render_section_header


def _render_map_column(default_alerts: list | None = None) -> None:
    """왼쪽 칸: 한반도 위성사진 + 경보 마커 지도. 마커를 누르면 EO/SAR 판독 페이지로 바로 이동한다.

    shared.tactical_map의 CCv2(진짜 양방향) 커스텀 지도를 쓴다 — 마커를 클릭하면
    Python으로 alert_id가 그대로 돌아온다.
    """
    render_section_header(
        "경보 상황 지도",
        "센서별 최신 변화 경보를 한반도 작전 지도에서 확인합니다.",
        badge="LIVE MAP",
    )

    # 센서 필터: 경보는 센서(EO/SAR)별 독립 체인으로 생성되므로, "전체"에서는
    # 지역별 최신 1건에 다른 센서의 경보가 가려질 수 있다. 센서를 고르면
    # 그 센서의 경보만 대상으로 지역별 최신 1건씩 표시한다.
    sensor_choice = st.segmented_control(
        "센서", ["전체", "EO", "SAR"], key="analyst_desk_sensor_filter", default="전체",
    )
    sensor = None if sensor_choice in (None, "전체") else sensor_choice

    try:
        tile_url = service.get_ee_tile_url()
    except Exception as exc:
        st.error(f"위성 지도 생성 실패: {exc}")
        return

    # 경보(alert_id) 목록을 DB에서 조회해 지도에 마커로 표시.
    # 색은 경보수준(긴급/중요/특이)에 따라 다르게 찍는다.
    if sensor is None and default_alerts is not None:
        alerts = default_alerts
    else:
        try:
            alerts = service.get_alerts(sensor)
        except Exception as exc:
            st.error(f"경보 조회 실패: {exc}")
            alerts = []

    if not alerts and sensor:
        st.info(f"{sensor} 경보가 없습니다.")

    st.html(
        """
        <div class="ui-map-legend" aria-label="경보 수준 범례">
          <span><i style="background:#DC2626"></i>긴급</span>
          <span><i style="background:#D97706"></i>중요</span>
          <span><i style="background:#2563EB"></i>특이</span>
          <span>마커 선택 시 EO/SAR 판독으로 이동</span>
        </div>
        """
    )

    clicked_alert_id = tactical_map.render_tactical_map(
        tile_url, alerts, service.NORTH_KOREA_BOUNDS,
        marker_label=service.marker_label,
        height=530,
        key="analyst_tactical_map",
        theme=st.session_state.get("ui_theme", "dark"),
    )
    if clicked_alert_id is not None:
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
        .properties(height=455)
        .configure_view(strokeOpacity=0)
        .configure_axis(
            gridColor="#223140",
            domainColor="#34495e",
            labelColor="#93a4b8",
            titleColor="#e7edf5",
            tickColor="#34495e",
        )
        .configure_legend(
            labelColor="#93a4b8",
            titleColor="#e7edf5",
            orient="bottom",
        )
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
    render_section_header(
        "최근 24시간 탐지 추이",
        "실제 탐지 건수와 2시간 이동 평균을 비교합니다.",
        badge="24 HOURS",
    )

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
    render_page_header(
        "분석 현황",
        "EO·SAR 변화 경보와 최근 탐지 추이를 한 화면에서 확인하고 판독 업무로 연결합니다.",
        eyebrow="ANALYST WORKSPACE",
        status="분석 시스템 정상",
    )

    try:
        summary_alerts = service.get_alerts()
    except Exception:
        summary_alerts = []

    urgent_count = sum(alert.alert_level == "URGENT" for alert in summary_alerts)
    important_count = sum(alert.alert_level == "IMPORTANT" for alert in summary_alerts)
    sensors = {alert.sensor_type for alert in summary_alerts if alert.sensor_type}
    render_metric_grid(
        [
            MetricItem("활성 경보", f"{len(summary_alerts)}건", "지역별 최신 경보", "primary"),
            MetricItem("긴급 경보", f"{urgent_count}건", "즉시 판독 필요", "danger"),
            MetricItem("중요 경보", f"{important_count}건", "우선순위 검토 대상", "warning"),
            MetricItem("운용 센서", f"{len(sensors)}종", "EO · SAR 연계", "sky"),
        ]
    )

    st.html('<div style="height:10px" aria-hidden="true"></div>')

    map_col, stats_col = st.columns([1.08, 0.92], gap="large")

    with map_col:
        with st.container(key="panel_analyst_map"):
            _render_map_column(summary_alerts)

    with stats_col:
        with st.container(key="panel_analyst_statistics"):
            _render_statistics_column()


def render_hq_desk_page() -> None:
    """Analyst Desk 페이지 진입점. 지도 + 최근 24시간 통계를 보여준다."""
    render_map_view()
