"""
[Alerts 도메인 - 화면]
판독관이 alert 테이블의 경보를 확인하고, 필요 시 보고서 초안을 직접 생성하는 페이지.
경보 분류는 change_analysis.py가 만들고, 이 화면은 조회/확인/보고 필요 판단만 담당한다.
"""
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from features.alerts import service


def render_alerts_page() -> None:
    """경보 확인 페이지 전체를 그린다."""
    st.title("경보 확인")
    st.caption("판독관이 미확인 경보를 확인하고, 보고 필요 여부를 수동으로 결정합니다.")

    level = st.radio("경보 등급", ["전체", "URGENT", "IMPORTANT", "NOTICE"], horizontal=True)
    status = st.radio("처리 상태", ["NEW", "CHECKED", "전체"], horizontal=True)
    level_filter: Optional[str] = None if level == "전체" else level
    status_filter: Optional[str] = None if status == "전체" else status

    try:
        alerts = service.fetch_alerts(level_filter, status_filter)
    except Exception as exc:
        st.error(f"경보 조회 실패: {exc}")
        return

    if not alerts:
        st.info("조회 조건에 맞는 경보가 없습니다.")
        return

    if st.button("미확인 경보 모두 확인 처리", use_container_width=True):
        try:
            updated = service.mark_all_checked()
        except Exception as exc:
            st.error(f"전체 확인 처리 실패: {exc}")
        else:
            st.success(f"{updated}건 확인 처리했습니다.")
            st.rerun()

    selected = _render_alert_table(alerts)
    if selected is not None:
        _render_alert_detail(selected)


def _render_alert_table(alerts: List[Dict]) -> Optional[Dict]:
    rows = [
        {
            "alert_id": item["alert_id"],
            "상태": item["alert_status"],
            "등급": item["alert_level"],
            "제목": item["title"],
            "장비": item["class_name"],
            "지역": item["region_name"],
            "센서": item["sensor_type"],
            "촬영시각": item["captured_time"],
            "보고": "있음" if item["has_report"] else "없음",
        }
        for item in alerts
    ]
    event = st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
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
    st.subheader("선택 경보 상세")
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
        if st.button("보고 필요: 초안 생성", use_container_width=True):
            try:
                report_id, created = service.ensure_report_draft(int(alert["alert_id"]))
            except Exception as exc:
                st.error(f"보고서 초안 생성 실패: {exc}")
            else:
                verb = "생성" if created else "기존 초안 확인"
                st.success(f"보고서 초안 {verb}: report_id={report_id}")
