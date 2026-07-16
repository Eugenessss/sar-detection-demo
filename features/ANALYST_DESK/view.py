import datetime

import altair as alt
import streamlit as st
from streamlit_folium import st_folium

from features.ANALYST_DESK import service
from features.statistics import service as stats_service
from shared.charts import apply_theme
from shared.ui import MetricItem, render_metric_grid, render_page_header, render_section_header

# 마커 클릭으로 어느 경보 좌표를 눌렀는지 판별할 때 쓰는 오차 허용치(도 단위, 약 100m).
_CLICK_MATCH_TOLERANCE = 0.001


# 이 페이지(로그인 첫 화면)는 위젯 상호작용마다 rerun되며 전체가 다시 실행된다.
# 아래 조회들을 짧은 TTL로 캐싱해, 필터·지도 클릭 때마다 같은 DB 조회를 반복하지
# 않게 한다(다른 페이지들과 동일한 @st.cache_data 패턴). 데이터가 초 단위로 바뀌지
# 않으므로 수십 초 캐시로도 화면 최신성은 충분하다.
@st.cache_data(ttl=30, show_spinner=False)
def _cached_alerts(sensor=None):
    return service.get_alerts(sensor)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_map_regions():
    return service.get_map_regions()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_region_latest():
    return stats_service.latest_captured_time_by_region()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_statistics(start, end):
    return stats_service.build_statistics(start, end)


def _find_alert_by_click(lat: float, lng: float, alerts: list) -> "service.Alert | None":
    """지도에서 클릭된 좌표와 가장 가까운(오차범위 내) 경보를 찾는다."""
    for alert in alerts:
        if abs(alert.latitude - lat) <= _CLICK_MATCH_TOLERANCE and \
           abs(alert.longitude - lng) <= _CLICK_MATCH_TOLERANCE:
            return alert
    return None


def _render_map_column(default_alerts: list | None = None) -> None:
    """왼쪽 칸: 한반도 위성사진 + 경보 마커 지도. 마커를 누르면 EO/SAR 판독 페이지로 바로 이동한다."""
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
        m = service.build_eo_map()
    except Exception as exc:
        st.error(f"위성 지도 생성 실패: {exc}")
        return

    # 경보(alert_id) 목록을 DB에서 조회해 지도에 마커로 표시.
    # 색은 경보수준(긴급/중요/특이)에 따라 다르게 찍는다.
    if sensor is None and default_alerts is not None:
        alerts = default_alerts
    else:
        try:
            alerts = _cached_alerts(sensor)
        except Exception as exc:
            st.error(f"경보 조회 실패: {exc}")
            alerts = []

    if not alerts and sensor:
        st.info(f"{sensor} 경보가 없습니다.")

    try:
        regions = _cached_map_regions()
    except Exception as exc:
        st.error(f"지역 조회 실패: {exc}")
        regions = []

    # 현재 센서 필터 기준으로 경보가 없는 지역은 초록색 정상 마커로 표시한다.
    # 정상 마커는 alerts에 포함되지 않으므로 클릭해도 경보 상세 화면으로 이동하지 않는다.
    alert_region_ids = {
        alert.region_id for alert in alerts if alert.region_id is not None
    }
    for region in regions:
        if region.region_id not in alert_region_ids:
            service.add_circle_marker(
                m, region.latitude, region.longitude,
                color=service.NORMAL_MARKER_COLOR,
                tooltip=f"[정상] 특이사항 없음",
            )

    for alert in alerts:
        level_label = service.marker_label(alert.alert_level)
        service.add_circle_marker(
            m, alert.latitude, alert.longitude,
            color=service.marker_color(alert.alert_level),
            tooltip=f"[{level_label}·{alert.sensor_type}] {alert.asset_name}",
        )

    st.html(
        """
        <div class="ui-map-legend" aria-label="경보 수준 범례">
          <span><i style="background:#DC2626"></i>긴급</span>
          <span><i style="background:#D97706"></i>중요</span>
          <span><i style="background:#2563EB"></i>특이</span>
          <span><i style="background:#16A34A"></i>정상</span>
          <span>경보 마커 선택 시 EO/SAR 판독으로 이동</span>
        </div>
        """
    )

    # 센서 필터를 key에 넣는다 — 필터를 바꾸면 지도를 새로 만들어, 직전 필터에서
    # 클릭했던 좌표가 남아 엉뚱한 경보로 넘어가는 것을 막는다.
    # 리셋 토큰도 넣는다 — EO/SAR로 이동했다가 상단 메뉴로 이 페이지에 돌아왔을 때
    # 같은 key를 계속 쓰면 이전 클릭 좌표를 그대로 기억하고 있어서, 돌아오자마자
    # 다시 클릭한 것처럼 인식해 또 이동해버리는 문제가 있다. 마커를 눌러 이동하기
    # 직전에 토큰을 올려두면(아래) 돌아왔을 때 지도 컴포넌트가 새로 만들어진다.
    map_key = f"analyst-desk-alert-map-{st.session_state.get('_analyst_desk_map_reset_token', 0)}-{sensor_choice}"
    map_data = st_folium(
        m, height=530,
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


def _render_region_chart(region: str, overlay_data, start, end) -> None:
    """한 지역의 실제(실선+점)/2시간 평균(점선) 추이 그래프 하나를 그린다.

    촬영 주기가 2시간이므로 X축 틱도 2시간 간격으로 고정하고, 축 범위는 조회 창
    [start, end] 전체로 잡아 데이터가 한쪽에 몰려도 창이 온전히 보이게 한다.
    데이터 시점이 많지 않아 선만으로는 놓치기 쉬워 각 시점에 점을 함께 찍는다.
    지역마다 창의 절대 시각이 다를 수 있어(각자 마지막 촬영 기준) 창 범위를
    캡션으로 함께 적어 축이 어긋나 보이는 것을 숨기지 않고 명시한다.
    """
    st.markdown(f"**{region}**")
    st.caption(f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M} · 마지막 촬영 시점 기준 24시간")
    if overlay_data.empty:
        st.info(f"{region}: 이 기간에 표시할 통계가 없습니다.")
        return

    # 촬영 주기(2시간)에 맞춘 X축 틱. Streamlit 내장 Vega가 tickCount의
    # TimeIntervalStep 표기를 지원하지 못해(빈 차트로 렌더링됨) 틱 값을 직접 나열한다.
    tick_values = [
        (start + datetime.timedelta(hours=2 * i)).isoformat()
        for i in range(int((end - start).total_seconds() // 7200) + 1)
    ]

    chart = (
        alt.Chart(overlay_data)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "captured_time:T",
                title=None,
                scale=alt.Scale(domain=[start.isoformat(), end.isoformat()]),
                axis=alt.Axis(format="%d일 %H시", labelAngle=-35, values=tick_values),
            ),
            y=alt.Y("detected_count:Q", title="탐지 수"),
            color=alt.Color("class_name:N", title="장비"),
            strokeDash=alt.StrokeDash("series:N", title="구분 (실제/평균)"),
            tooltip=["class_name", "series", "captured_time:T", "detected_count:Q"],
        )
        .properties(height=200)
    )
    st.altair_chart(apply_theme(chart), use_container_width=True)


def _render_statistics_detail_button() -> None:
    """그래프 아래: statistics 페이지(장소·장비·기간을 자유롭게 조회하는 전체 통계 화면)로 이동하는 버튼."""
    if st.button("상세 통계", use_container_width=True, key="analyst_desk_go_statistics"):
        statistics_page = st.session_state.get("_pages_by_url", {}).get("statistics")
        if statistics_page is None:
            st.error("Statistics 페이지를 찾을 수 없습니다.")
        else:
            st.switch_page(statistics_page)


def _render_statistics_column() -> None:
    """오른쪽 칸: 지역(개풍군/원산시)별 24시간 탐지 추이를 위아래 두 그래프로 보여주고,
    그 아래에 상세 통계 페이지로 이동하는 버튼을 둔다.

    지역마다 촬영 주기가 어긋날 수 있어(예: 한 지역만 데이터가 하루 최신), 전역 최신
    한 시점으로 창을 잡으면 뒤처진 지역이 통째로 빠진다. 그래서 각 지역을 '그 지역의
    마지막 촬영시각 기준 24시간'으로 따로 잡아, 두 지역이 항상 각자 그려지게 한다.
    대신 창의 절대 시각이 지역마다 다를 수 있으므로 각 차트에 창 범위를 캡션으로 명시한다.
    """
    render_section_header(
        "지역별 24시간 탐지 추이",
        "지역마다 마지막 촬영 시점 기준 24시간의 실제 탐지와 2시간 구간 평균을 비교합니다.",
        badge="24 HOURS",
    )

    try:
        region_latest = _cached_region_latest()
    except Exception as exc:
        st.error(f"통계 조회 실패: {exc}")
        _render_statistics_detail_button()
        return

    if not region_latest:
        st.warning("조회된 탐지 결과가 없습니다.")
        _render_statistics_detail_button()
        return

    with st.spinner("통계 조회 중..."):
        for region in sorted(region_latest):
            latest = region_latest[region]
            start, end = stats_service.resolve_range(
                latest - datetime.timedelta(hours=24), "24시간"
            )  # end == latest (그 지역의 마지막 촬영시각)
            result = _cached_statistics(start, end)
            if result is None:
                st.markdown(f"**{region}**")
                st.caption(
                    f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M} · 마지막 촬영 시점 기준 24시간"
                )
                st.info(f"{region}: 이 기간에 표시할 통계가 없습니다.")
                continue
            # build_two_hour_overlay는 창 끝(end=최신 촬영시각)의 점을 `< end`로 잘라낸다.
            # 그 최신 점이 그래프에서 사라지지 않도록(특히 신규 촬영 1건만 든 지역)
            # overlay 계산에는 끝을 1초 넘겨 최신 점까지 포함시키되, 차트 축 범위는
            # 깔끔한 2시간 눈금을 위해 end(=latest) 그대로 쓴다.
            overlay_data = stats_service.build_two_hour_overlay(
                result.raw, start, end + datetime.timedelta(seconds=1), region
            )
            _render_region_chart(region, overlay_data, start, end)

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
        summary_alerts = _cached_alerts()
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
