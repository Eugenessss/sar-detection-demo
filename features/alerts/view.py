"""
[Alerts 도메인 - 화면]
판독관이 alert 테이블의 경보를 확인하고, 필요 시 보고서 초안을 직접 생성하는 페이지.
경보 분류는 change_analysis.py가 만들고, 이 화면은 조회/확인/보고 필요 판단만 담당한다.
"""
from contextlib import nullcontext
from typing import Dict, List, Optional, Sequence, Union

import pandas as pd
import streamlit as st

from features.alerts import service
from shared.ui import MetricItem, render_metric_grid, render_page_header, render_section_header

# alert_level(enum 원본값) -> 표에 보여줄 색상 마커(텍스트 없이 마커만).
_LEVEL_DISPLAY = {
    "URGENT": "🔴",
    "IMPORTANT": "🟠",
    "NOTICE": "🔵",
}


def render_alerts_page(
    *,
    show_caption: bool = True,
    show_level_filter: bool = True,
    level_options: Optional[List[str]] = None,
    level_legend: Optional[str] = None,
    legend_help_text: Optional[str] = None,
    fixed_levels: Optional[Sequence[str]] = None,
    show_status_filter: bool = True,
    show_mark_all_button: bool = True,
    hidden_columns: Optional[List[str]] = None,
    enable_row_selection: bool = True,
    table_height: Optional[int] = None,
    table_top_spacer_px: int = 0,
    level_row_spacer_px: int = 0,
    navigate_on_select_url_path: Optional[str] = None,
    own_url_path: Optional[str] = None,
) -> None:
    """경보 확인 페이지 전체를 그린다.

    HQ Desk 화면 오른쪽에 축소판으로 재사용할 수 있도록 옵션을 받는다
    (옵션을 안 주면 Alerts 메뉴 페이지와 동일한 전체 기능). *_spacer_px 값들은 옆
    (HQ Desk 지도 쪽) 요소들과 높이를 맞추기 위한 여백으로, level_row_spacer_px는
    "경보 등급" 줄 위, table_top_spacer_px는 표 위에 들어간다.
    show_level_filter=False면 등급을 고를 수 있는 라디오 대신, level_legend 문구를
    보여주고 fixed_levels로 고정된 등급들만 조회한다. legend_help_text가 있으면
    level_legend 바로 아래에 작은 안내 문구로 덧붙인다.
    navigate_on_select_url_path가 있으면, 행을 선택했을 때 그 자리에서 상세를 그리는
    대신 그 url_path 페이지로 이동하며 alert_id(및 own_url_path가 있으면 back_to)를
    쿼리 파라미터로 넘긴다 (HQ Desk의 축소판 목록에서 Alerts 메뉴 페이지로 넘어가
    상세를 보는 용도). own_url_path는 지금 이 화면 자신의 url_path로, 이동한 쪽에서
    "돌아가기" 버튼을 이 화면으로 다시 연결하는 데 쓰인다.
    """
    # HQ Desk 등 다른 곳에서 alert_id를 쿼리 파라미터로 넘겨 이 페이지로 이동해 온
    # 경우, 판독관 전용 기능(등급/상태 필터·확인 처리·전체 표) 없이 그 경보 하나만
    # 읽기 전용으로 보여주고 끝낸다. navigate_on_select_url_path가 있다는 건 지금
    # 호출된 곳이 "다른 페이지로 보내는" 축소판(예: HQ Desk 임베드)이라는 뜻이라,
    # 정작 그 화면에서는 검사하지 않는다 — 안 그러면 alert_id 쿼리 파라미터가 페이지
    # 전환 후에도 남아있어서, HQ Desk로 돌아왔을 때도 상세가 또 떠버린다.
    if not navigate_on_select_url_path:
        focused_alert_id = st.query_params.get("alert_id")
        if focused_alert_id:
            _render_focused_alert_view(focused_alert_id)
            return

    if show_caption:
        render_page_header(
            "경보 확인",
            "변화 탐지 경보를 등급과 처리 상태별로 확인하고 후속 보고 여부를 판단합니다.",
            eyebrow="ALERT TRIAGE",
            status="경보 체계 연결",
        )
    else:
        render_section_header(
            "우선 경보",
            "긴급·중요 경보를 우선순위 순으로 확인합니다.",
            badge="PRIORITY",
        )

    filter_panel = st.container(key="panel_alert_filters") if show_caption else nullcontext()
    with filter_panel:
        if show_caption:
            render_section_header(
                "경보 조회 조건",
                "등급과 처리 상태를 조합해 검토 대상을 빠르게 좁힙니다.",
                badge="FILTER",
            )

        if level_row_spacer_px:
            st.markdown(f"<div style='height:{level_row_spacer_px}px;'></div>", unsafe_allow_html=True)

        level_filter: Optional[Union[str, Sequence[str]]]
        if show_level_filter:
            # segmented_control은 선택을 해제해 None을 돌려줄 수 있으므로 "전체"와 같게 취급한다.
            options = level_options or ["전체", "URGENT", "IMPORTANT", "NOTICE"]
            level = st.segmented_control(
                "경보 등급", options, default=options[0], key="alerts_level_filter",
            )
            level_filter = None if level in (None, "전체") else level
        else:
            if level_legend:
                st.caption(level_legend)
            if legend_help_text:
                st.caption(legend_help_text)
            level_filter = fixed_levels

        status_filter: Optional[str] = None
        if show_status_filter:
            status = st.segmented_control(
                "처리 상태", ["NEW", "CHECKED", "전체"], default="NEW", key="alerts_status_filter",
            )
            status_filter = None if status in (None, "전체") else status

    try:
        alerts = service.fetch_alerts(level_filter, status_filter)
    except Exception as exc:
        st.error(f"경보 조회 실패: {exc}")
        return

    if not alerts:
        st.info("조회 조건에 맞는 경보가 없습니다.")
        return

    if show_caption:
        urgent_count = sum(item["alert_level"] == "URGENT" for item in alerts)
        important_count = sum(item["alert_level"] == "IMPORTANT" for item in alerts)
        new_count = sum(item["alert_status"] == "NEW" for item in alerts)
        render_metric_grid(
            [
                MetricItem("조회 경보", f"{len(alerts)}건", "현재 조건 기준", "primary"),
                MetricItem("미확인", f"{new_count}건", "확인 처리 필요", "warning"),
                MetricItem("긴급", f"{urgent_count}건", "즉시 검토", "danger"),
                MetricItem("중요", f"{important_count}건", "우선 검토", "sky"),
            ]
        )

    table_panel = st.container(key="panel_alert_table") if show_caption else nullcontext()
    with table_panel:
        if show_caption:
            render_section_header(
                "경보 목록",
                "행을 선택하면 상세 메시지와 후속 처리 기능이 열립니다.",
                badge=f"{len(alerts)} ALERTS",
            )

        if show_mark_all_button:
            if st.button("미확인 경보 모두 확인 처리", use_container_width=True):
                try:
                    updated = service.mark_all_checked()
                except Exception as exc:
                    st.error(f"전체 확인 처리 실패: {exc}")
                else:
                    st.success(f"{updated}건 확인 처리했습니다.")
                    st.rerun()

        if table_top_spacer_px:
            st.markdown(f"<div style='height:{table_top_spacer_px}px;'></div>", unsafe_allow_html=True)

        selected = _render_alert_table(
            alerts,
            hidden_columns=hidden_columns,
            enable_selection=enable_row_selection,
            height=table_height,
        )
    if selected is not None:
        if navigate_on_select_url_path:
            target_page = st.session_state.get("_pages_by_url", {}).get(navigate_on_select_url_path)
            if target_page is None:
                st.error(f"'{navigate_on_select_url_path}' 페이지를 찾을 수 없습니다.")
            else:
                query_params = {"alert_id": str(selected["alert_id"])}
                if own_url_path:
                    query_params["back_to"] = own_url_path
                st.switch_page(target_page, query_params=query_params)
        else:
            _render_alert_detail(selected)


def _render_focused_alert_view(focused_alert_id: str) -> None:
    """다른 화면(예: Commander Desk)에서 alert_id 쿼리 파라미터를 달고 넘어왔을 때,
    판독관 전용 기능 없이 그 경보 하나만 읽기 전용으로 보여준다.

    쿼리 파라미터에 back_to(원래 화면의 url_path)가 있으면 그리로 돌아가는
    버튼도 맨 위에 둔다.
    """
    render_page_header(
        "경보 상세",
        "선택한 경보의 발생 근거와 표적·지역·센서 정보를 확인합니다.",
        eyebrow="ALERT DETAIL",
    )

    back_to = st.query_params.get("back_to")
    if back_to:
        target_page = st.session_state.get("_pages_by_url", {}).get(back_to)
        if target_page is not None and st.button("← 돌아가기"):
            st.query_params.clear()
            st.switch_page(target_page)

    try:
        alert = service.fetch_alert_by_id(int(focused_alert_id))
    except Exception as exc:
        st.error(f"경보 조회 실패: {exc}")
        return

    if alert is None:
        st.warning("경보를 찾을 수 없습니다.")
        return

    level_label = _LEVEL_DISPLAY.get(alert["alert_level"], alert["alert_level"])
    with st.container(key="panel_alert_detail"):
        render_section_header(
            f"{level_label} {alert['title']}",
            "경보 발생 근거와 변화량을 확인합니다.",
            badge=alert["alert_level"],
        )
        st.write(alert["message"])
        st.caption(
            f"{alert['asset_name']} / {alert['region_name']} / {alert['sensor_type']} | "
            f"{alert['event_type']} {alert['previous_count']} -> {alert['current_count']} "
            f"(delta {alert['delta_count']})"
        )


def _render_alert_table(
    alerts: List[Dict],
    *,
    hidden_columns: Optional[List[str]] = None,
    enable_selection: bool = True,
    height: Optional[int] = None,
) -> Optional[Dict]:
    hidden = set(hidden_columns or [])
    rows = [
        {
            key: value
            for key, value in {
                "alert_id": item["alert_id"],
                "상태": item["alert_status"],
                "등급": _LEVEL_DISPLAY.get(item["alert_level"], item["alert_level"]),
                "제목": item["title"],
                "장비": item["class_name"],
                "지역": item["region_name"],
                "센서": item["sensor_type"],
                "촬영시각": item["captured_time"],
                "보고": "있음" if item["has_report"] else "없음",
            }.items()
            if key not in hidden
        }
        for item in alerts
    ]

    # "지역"은 이름이 길면(예: 원산비행장, 근위 제6보병사단) 다른 컬럼에 밀려 한 글자만
    # 보이도록 잘리곤 해서, 폭을 넉넉히 잡아 전체가 한눈에 보이게 한다.
    column_config = {"지역": st.column_config.TextColumn("지역", width="large")}

    if not enable_selection:
        # 체크박스 선택 UI 없이 목록만 훑어보는 용도(예: HQ Desk 축소판)라, 클릭 선택도 없다.
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            height=height,
            column_config=column_config,
        )
        return None

    event = st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=column_config,
        on_select="rerun",
        selection_mode="single-row",
        key="alerts_table",
    )

    selection = getattr(event, "selection", {})
    selected_rows = list(selection.get("rows", [])) if isinstance(selection, dict) else []
    if not selected_rows:
        st.caption("행을 선택하면 상세 메시지와 처리 버튼이 표시됩니다.")
        return None

    index = selected_rows[0]
    return alerts[index] if 0 <= index < len(alerts) else None


def _render_alert_detail(alert: Dict) -> None:
    with st.container(key="panel_alert_detail"):
        render_section_header(
            "선택 경보 상세",
            "경보 내용을 확인하고 처리 또는 상세 메시지 생성을 진행합니다.",
            badge=alert["alert_status"],
        )
        st.write(alert["message"])
        st.caption(
            f"{alert['asset_name']} / {alert['region_name']} / {alert['sensor_type']} | "
            f"{alert['event_type']} {alert['previous_count']} -> {alert['current_count']} "
            f"(delta {alert['delta_count']})"
        )

        left, right = st.columns(2)
        with left:
            disabled = alert["alert_status"] == "CHECKED"
            if st.button("판독관 확인 처리", disabled=disabled, use_container_width=True):
                try:
                    service.mark_checked(int(alert["alert_id"]))
                except Exception as exc:
                    st.error(f"확인 처리 실패: {exc}")
                else:
                    st.success("확인 처리했습니다.")
                    st.rerun()

        with right:
            if st.button("상세 메세지 생성", use_container_width=True):
                try:
                    report_id, created = service.ensure_report_draft(int(alert["alert_id"]))
                except Exception as exc:
                    st.error(f"상세 메세지 생성 실패: {exc}")
                else:
                    verb = "생성" if created else "기존 메세지 확인"
                    st.success(f"상세 메세지 {verb}: report_id={report_id}")

    # 버튼 처리 뒤에 조회하므로, 방금 생성한 초안도 같은 화면에서 바로 보인다.
    _render_report_detail(int(alert["alert_id"]))


def _render_report_detail(alert_id: int) -> None:
    """선택 경보에 연결된 메세지 상세(제목·상태·작성자·요약)를 보여준다."""
    try:
        report = service.fetch_report(alert_id)
    except Exception as exc:
        st.warning(f"메세지 조회 실패: {exc}")
        return
    if report is None:
        return

    with st.container(key="panel_alert_report"):
        render_section_header(
            "메시지 상세",
            "선택 경보에 연결된 보고 메시지입니다.",
            badge="REPORT",
        )
        status_label = "배포됨" if report["report_status"] == "DISTRIBUTED" else "초안"
        st.markdown(f"**{report['title']}**")
        meta = (
            f"report_id={report['report_id']} | 상태: {status_label} | "
            f"작성자: {report['user_name']} ({report['role']})"
        )
        if report["distributed_at"]:
            meta += f" | 배포시각: {report['distributed_at']}"
        st.caption(meta)
        st.write(report["summary"])
