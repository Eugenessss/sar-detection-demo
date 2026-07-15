from typing import Optional

import streamlit as st

from features.alerts.view import render_alerts_page
from features.HQ_DESK import detail_view, service
from shared import tactical_map
from shared.ui import MetricItem, render_metric_grid, render_page_header, render_section_header

# 지도(왼쪽) : 경보 확인 목록(오른쪽) 컬럼 폭 비율. 지도를 아주 살짝 줄이고
# 표를 약간 키워서, "지역" 컬럼(예: 개풍군)이 한눈에 다 보이도록 한다.
_MAP_COLUMN_RATIO = [3, 1]

# 지도와 오른쪽 경보 확인 표의 높이를 맞추기 위해 공유하는 값(px).
_MAP_HEIGHT_PX = 600


def _render_map(
    sensor: Optional[str],
    sensor_choice: Optional[str],
    default_alerts: Optional[list] = None,
) -> None:
    """한반도 위성사진 + 경보 마커 지도를 그린다. 마커를 누르면 상세 화면으로 전환한다.

    shared.tactical_map의 CCv2(진짜 양방향) 커스텀 지도를 쓴다 — 마커를 클릭하면
    Python으로 alert_id가 그대로 돌아와서 클릭 한 번으로 상세 화면 전환이 된다.
    """
    try:
        tile_url = service.get_ee_tile_url()
    except Exception as exc:
        st.error(f"위성 지도 생성 실패: {exc}")
        return

    # 경보(alert_id) 목록을 DB에서 조회해 지도에 마커로 표시. 색은 경보수준(긴급/중요)에
    # 따라 다르게 찍는다. 지휘관 화면은 특이(NOTICE)급은 안 쓰기로 해서, 오른쪽 경보
    # 확인 목록(fixed_levels)과 똑같이 지도에서도 뺀다.
    if sensor is None and default_alerts is not None:
        alerts = [a for a in default_alerts if a.alert_level != "NOTICE"]
    else:
        try:
            alerts = [a for a in service.get_alerts(sensor) if a.alert_level != "NOTICE"]
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
          <span>마커 선택 시 경보 상세로 이동</span>
        </div>
        """
    )

    clicked_alert_id = tactical_map.render_tactical_map(
        tile_url, alerts, service.KOREA_PENINSULA_BOUNDS,
        marker_label=service.marker_label,
        height=_MAP_HEIGHT_PX,
        key="hq_tactical_map",
    )
    if clicked_alert_id is not None:
        st.session_state["selected_alert_id"] = clicked_alert_id
        st.session_state["view"] = "detail"
        st.rerun()


def render_map_view() -> None:
    """왼쪽에 경보 지도, 오른쪽에 경보 확인 목록(Alerts 화면 축소판)을 나란히 그린다.

    두 컬럼의 제목(지휘관 페이지 / 경보 확인) 높이를 맞추기 위해, 지도 쪽 제목·센서
    필터를 컬럼 밖이 아니라 map_col 안 첫머리에 둔다 (컬럼은 시작 지점이 서로 같다).
    """
    render_page_header(
        "지휘관 현황",
        "주요 변화 경보와 작전 지역을 통합 확인하고 우선순위 경보의 상세 판단으로 연결합니다.",
        eyebrow="COMMANDER WORKSPACE",
        status="지휘통제 시스템 정상",
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
            MetricItem("주요 경보", f"{urgent_count + important_count}건", "긴급·중요 경보", "primary"),
            MetricItem("긴급", f"{urgent_count}건", "즉시 상황 판단", "danger"),
            MetricItem("중요", f"{important_count}건", "우선 검토 대상", "warning"),
            MetricItem("감시 센서", f"{len(sensors)}종", "EO · SAR 통합", "sky"),
        ]
    )

    st.html('<div style="height:10px" aria-hidden="true"></div>')
    map_col, alerts_col = st.columns(_MAP_COLUMN_RATIO, gap="large")

    with map_col:
        with st.container(key="panel_hq_map"):
            render_section_header(
                "작전 상황 지도",
                "지역별 최신 경보와 센서 정보를 지도에서 확인합니다.",
                badge="LIVE MAP",
            )

            # 센서 필터: 경보는 센서(EO/SAR)별 독립 체인으로 생성되므로, "전체"에서는
            # 지역별 최신 1건에 다른 센서의 경보가 가려질 수 있다. 센서를 고르면
            # 그 센서의 경보만 대상으로 지역별 최신 1건씩 표시한다.
            sensor_choice = st.segmented_control(
                "센서", ["전체", "EO", "SAR"], key="hq_sensor_filter", default="전체",
            )
            sensor = None if sensor_choice in (None, "전체") else sensor_choice

            _render_map(sensor, sensor_choice, summary_alerts)

    with alerts_col:
        # 지휘관 화면에서는: 안내 문구·처리상태 필터·전체 확인 버튼은 불필요하고,
        # alert_id·상태·센서·보고 컬럼도 뺀다. 지도에 애초에 URGENT/IMPORTANT급만
        # 표시되므로, 고를 필요 없이 그 둘로 고정하고 라디오 대신 지도 범례와 같은
        # 문구만 보여준다. 표 높이도 지도와 맞춘다. 행을 선택하면(체크박스) 여기서
        # 바로 상세를 그리는 대신, 상단 메뉴의 Alerts 페이지로 넘어가 그 경보 상세를
        # 보여준다 (지도 마커 클릭 → 상세 화면 전환과 같은 맥락).
        with st.container(key="panel_hq_alerts"):
            render_alerts_page(
                show_caption=False,
                show_level_filter=False,
                level_legend="🔴 긴급" + " " * 8 + "🟠 중요",
                legend_help_text="체크박스를 선택하면 해당 경보의 상세 정보로 이동합니다.",
                fixed_levels=["URGENT", "IMPORTANT"],
                show_status_filter=False,
                show_mark_all_button=False,
                hidden_columns=["alert_id", "상태", "센서", "보고"],
                enable_row_selection=True,
                navigate_on_select_url_path="alerts",
                own_url_path="hq-desk",
                table_height=_MAP_HEIGHT_PX,
                level_row_spacer_px=10,
                table_top_spacer_px=20,
            )


def render_hq_desk_page() -> None:
    """HQ Desk 페이지 진입점. 기본은 지도, 마커 클릭 시 세션 상태로 상세 화면으로 전환한다."""
    if st.session_state.get("view") == "detail":
        detail_view.render_alert_detail_page()
    else:
        render_map_view()
