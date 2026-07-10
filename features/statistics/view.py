"""
[통계 조회 화면]
탐지 결과(detection_result)를 기간별로 집계해 시계열 그래프·원본 표·통계 보고서를 보여주는 페이지.
흐름: 장소 선택 + 시작일 + 기간 선택 → service.build_statistics 호출 → 그래프/표 표시 → 보고서(.html) 생성.
조회 로직은 statistics/service.py를, 보고서 작성은 statistics/report.py를 직접 부른다.
레이아웃: 왼쪽 좁은 칸에 장소 선택·조회 기간 컨트롤을 몰아넣고, 오른쪽 넓은 칸에 그래프를 제목 바로 아래 배치한다.
"""
import datetime

import streamlit as st

from features.statistics import report, service

_INTERVAL_LABELS = list(service.INTERVALS.keys())


def render_location_control() -> str:
    """왼쪽 칸 맨 위: 장소 선택 팝오버를 그리고, 선택된 region_name을 돌려준다 ("전체"면 필터 없음)."""
    with st.popover("장소 선택"):
        try:
            regions = service.list_regions()
        except Exception as exc:
            st.error(f"지역 목록 조회 실패: {exc}")
            regions = []
        return st.selectbox("지역 (region_name)", ["전체"] + regions, key="stats_region")


def render_period_controls() -> tuple:
    """왼쪽 칸: 시작일 입력·기간 선택 버튼·조회범위 안내를 세로로 몰아 그리고, (시작시각, 종료시각)을 돌려준다."""
    st.subheader("조회 기간")
    start_date = st.date_input("시작일", value=datetime.date.today())

    if "stats_interval" not in st.session_state:
        st.session_state.stats_interval = service.DEFAULT_INTERVAL

    st.markdown("**기간 선택**")
    for label in _INTERVAL_LABELS:
        if st.button(label, use_container_width=True, key=f"interval_{label}"):
            st.session_state.stats_interval = label
    interval_label = st.session_state.stats_interval

    start, end = service.resolve_range(start_date, interval_label)
    st.info(f"**조회 범위** ({interval_label})\n\n{start} ~ {end}")

    return start, end


def render_graph_column(start: datetime.datetime, end: datetime.datetime, region: str) -> None:
    """오른쪽 칸: 탐지 통계를 조회해 그래프를 제목 바로 아래 그리고, 그 아래 원본 표를 붙인다."""
    with st.spinner("통계 조회 중..."):
        try:
            result = service.build_statistics(start, end)
        except Exception as exc:
            st.error(f"통계 조회 실패: {exc}")
            st.stop()

    if result is None:
        st.warning("해당 기간에 조회된 탐지 결과가 없습니다.")
        return

    st.subheader("시간대별 탐지 추이")
    selected_region = None if region == "전체" else region
    time_series = service.pivot_time_series(result.raw, selected_region)
    st.line_chart(time_series, use_container_width=True)

    with st.expander("원본 조회 결과"):
        st.dataframe(result.raw, use_container_width=True, hide_index=True)

    render_report_section(start, end, region, time_series)


def render_report_section(
    start: datetime.datetime,
    end: datetime.datetime,
    region_label: str,
    time_series,
) -> None:
    """원본 조회 결과 아래: 담당 분석관·분석 내용을 입력받아 통계 보고서(.docx)를 만들어 내려받는다."""
    st.subheader("통계 보고서")
    analyst_name = st.text_input("담당 분석관", key="report_analyst_name")
    analysis_text = st.text_area(
        "분석 내용",
        key="report_analysis_text",
        height=150,
        placeholder="보고서에 실릴 분석 내용을 입력하세요.",
    )

    report_html = report.build_statistics_report(
        start=start,
        end=end,
        region_label=region_label,
        analyst_name=analyst_name,
        analysis_text=analysis_text,
        time_series=time_series,
    )
    st.download_button(
        "통계 보고서 다운로드 (.html)",
        data=report_html,
        file_name=f"{start:%Y%m%d}_{region_label}_통계보고서.html",
        mime="text/html",
        use_container_width=True,
    )


def render_statistics_page() -> None:
    """통계 페이지 전체를 그린다: 왼쪽 좁은 칸(장소 선택 + 조회 기간) + 오른쪽 넓은 칸(그래프, 제목 바로 아래)."""
    st.title("탐지 통계")
    st.caption("기간별 장비 탐지 추이 (왼쪽 장소 선택으로 지역 필터 가능)")

    controls_col, graph_col = st.columns([1, 3])

    with controls_col:
        region = render_location_control()
        start, end = render_period_controls()

    with graph_col:
        render_graph_column(start, end, region)