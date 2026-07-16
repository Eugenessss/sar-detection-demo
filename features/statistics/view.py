"""
[통계 조회 화면]
탐지 결과(detection_result)를 기간별로 집계해 시계열 그래프·원본 표·통계 보고서를 보여주는 페이지.
흐름: 장소 선택 + 시작일 + 기간 선택 + 장비 선택 → service.build_statistics 호출 → 그래프/표 표시 → 보고서(.html) 생성.
조회 로직은 statistics/service.py를, 보고서 작성은 statistics/report.py를 직접 부른다.
레이아웃: 왼쪽 좁은 칸에 장소 선택·조회 기간·장비 선택 컨트롤을 몰아넣고, 오른쪽 넓은 칸에 그래프를 제목 바로 아래 배치한다.
"""
import calendar
import datetime
from typing import List, Optional

import altair as alt
import streamlit as st

from features.statistics import report, service
from shared.charts import apply_theme
from shared.ui import render_page_header, render_section_header

_INTERVAL_LABELS = list(service.INTERVALS.keys())


# 이 페이지도 위젯 상호작용마다 rerun되어 전체가 다시 실행되므로, DB 조회를 캐싱해
# 필터를 바꿀 때마다 같은 조회를 반복하지 않게 한다. 지역·장비 목록은 거의 변하지
# 않는 참조 데이터라 TTL을 길게, 통계 집계는 짧게 잡는다.
@st.cache_data(ttl=300, show_spinner=False)
def _cached_regions():
    return service.list_regions()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_equipment_classes(threat_levels):
    return service.list_equipment_classes(threat_levels)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_latest():
    return service.latest_captured_time()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_statistics(start, end):
    return service.build_statistics(start, end)


def _set_stats_region(region_name: str) -> None:
    """장소 버튼 콜백: 다음 화면 렌더링 전에 선택 지역을 갱신한다."""
    st.session_state["stats_region"] = region_name


def render_location_control() -> str:
    """왼쪽 칸 맨 위: 장소 선택 팝오버 하나를 그리고, 그 안에 지역 이름을 버튼으로 바로 나열한다.
    선택된 region_name을 돌려준다 ("전체"면 필터 없음)."""
    try:
        regions = _cached_regions()
    except Exception as exc:
        st.error(f"지역 목록 조회 실패: {exc}")
        regions = []

    if "stats_region" not in st.session_state:
        st.session_state.stats_region = "전체"

    with st.popover(f"장소 선택 ({st.session_state.stats_region})", use_container_width=True):
        for region_name in ["전체"] + regions:
            st.button(
                region_name,
                use_container_width=True,
                key=f"region_{region_name}",
                on_click=_set_stats_region,
                args=(region_name,),
            )

    return st.session_state.stats_region


def render_equipment_controls() -> Optional[List[str]]:
    """왼쪽 칸: 위협등급(threat_level 1/2/3) 체크박스로 먼저 거른 뒤,
    그 등급에 속한 장비만 장비 선택 팝오버에 체크박스로 올려 고른 장비(class_name) 목록을 돌려준다 (없으면 None)."""
    st.markdown("**위협등급 필터**")
    selected_threat_levels = st.pills(
        "위협등급",
        service.THREAT_LEVELS,
        selection_mode="multi",
        default=service.THREAT_LEVELS,
        format_func=lambda level: f"위협도 {level}",
        key="stats_threat_levels",
        label_visibility="collapsed",
    )

    if not selected_threat_levels:
        st.caption("위협등급을 하나 이상 선택하면 장비 목록이 표시됩니다.")
        return []

    try:
        equipment_classes = _cached_equipment_classes(selected_threat_levels)
    except Exception as exc:
        st.error(f"장비 목록 조회 실패: {exc}")
        return None

    selected = []
    with st.popover("장비 선택", use_container_width=True):
        columns = st.columns(3)
        for i, class_name in enumerate(equipment_classes):
            with columns[i % 3]:
                if st.checkbox(class_name, value=True, key=f"equipment_{class_name}"):
                    selected.append(class_name)

    return selected if equipment_classes else None


def render_period_controls() -> tuple:
    """왼쪽 칸: 시작 일시(연/월/일/시 선택)·기간 선택 버튼·조회범위 안내를 세로로 몰아 그리고, (시작시각, 종료시각)을 돌려준다."""
    today = datetime.date.today()
    if "stats_start_year" not in st.session_state:
        # 첫 진입 기본 조회 창은 "마지막 촬영일을 포함한 최근 <기본기간>"으로 잡는다.
        # resolve_range는 시작에서 기간만큼 앞(미래)으로 뻗으므로, 마지막 촬영일을 그대로
        # 시작으로 두면 창이 빈 미래로 향해 첫 화면이 비어 보인다. 그래서 창이 마지막
        # 촬영일 다음 0시에 끝나도록(=그 날 데이터까지 포함) 시작일을 기간만큼 뒤로 당긴다.
        try:
            anchor = _cached_latest()
        except Exception:
            anchor = None
        anchor_date = anchor.date() if anchor is not None else today
        if anchor_date.year < today.year - 5:   # 연 선택지 범위(최근 5년) 밖이면 오늘 기준
            anchor_date = today
        window_end = datetime.datetime.combine(anchor_date, datetime.time()) + datetime.timedelta(days=1)
        base_start = window_end - service.INTERVALS[service.DEFAULT_INTERVAL]
        if base_start.year < today.year - 5:   # 당긴 시작이 연 선택지 밖이면 촬영일 당일로
            base_start = datetime.datetime.combine(anchor_date, datetime.time())
        st.session_state.stats_start_year = base_start.year
        st.session_state.stats_start_month = base_start.month
        st.session_state.stats_start_day = base_start.day
        st.session_state.stats_start_hour = base_start.hour

    st.markdown("**시작 일시**")
    year_col, month_col, day_col, hour_col = st.columns(4)
    with year_col:
        year = st.selectbox(
            "연", list(range(today.year - 5, today.year + 1)),
            format_func=lambda y: f"{y}년", key="stats_start_year",
        )
    with month_col:
        month = st.selectbox(
            "월", list(range(1, 13)),
            format_func=lambda m: f"{m}월", key="stats_start_month",
        )

    max_day = calendar.monthrange(year, month)[1]
    if st.session_state.stats_start_day > max_day:
        st.session_state.stats_start_day = max_day

    with day_col:
        day = st.selectbox(
            "일", list(range(1, max_day + 1)),
            format_func=lambda d: f"{d}일", key="stats_start_day",
        )
    with hour_col:
        hour = st.selectbox(
            "시", list(range(24)),
            format_func=lambda h: f"{h}시", key="stats_start_hour",
        )

    start = datetime.datetime(year, month, day, hour)

    st.markdown("**기간 선택**")
    # segmented_control은 선택 상태를 위젯이 직접 강조하므로 별도 CSS 주입이 필요 없다.
    # 선택을 해제하면 None이 돌아오므로 기본 기간으로 되돌린다.
    selected_interval = st.segmented_control(
        "기간 선택",
        _INTERVAL_LABELS,
        default=service.DEFAULT_INTERVAL,
        key="stats_interval",
        label_visibility="collapsed",
    )
    interval_label = selected_interval or service.DEFAULT_INTERVAL

    start, end = service.resolve_range(start, interval_label)
    st.info(f"**조회 범위** ({interval_label})\n\n{start} ~ {end}")

    return start, end, interval_label




def _render_actual_vs_average_chart(
    overlay_data,
    empty_message: str,
    *,
    domain: Optional[List[str]] = None,
    tick_values: Optional[List[str]] = None,
) -> None:
    """실제(실선+점)/평균(점선) 겹쳐그리기 장문형 데이터를 장비별 색상으로 그린다 (1년·24시간 오버레이 공용).

    domain·tick_values를 주면 X축 범위와 틱 시각을 고정한다 (24시간 조회처럼 촬영
    주기가 일정한 경우). Streamlit 내장 Vega가 tickCount의 TimeIntervalStep을
    지원하지 못해 틱 값을 직접 나열하며, 축을 고정한 차트에는 .interactive()를
    걸지 않는다 (명시적 도메인과 스케일 바인딩이 얽히는 것을 피한다).
    """
    if overlay_data.empty:
        st.info(empty_message)
        return

    x_kwargs = {}
    if domain is not None:
        x_kwargs["scale"] = alt.Scale(domain=domain)
    if tick_values is not None:
        x_kwargs["axis"] = alt.Axis(format="%d일 %H시", labelAngle=-35, values=tick_values)

    chart = (
        alt.Chart(overlay_data)
        .mark_line(point=True)
        .encode(
            x=alt.X("captured_time:T", title="촬영시각", **x_kwargs),
            y=alt.Y("detected_count:Q", title="탐지 수"),
            color=alt.Color("class_name:N", title="장비"),
            strokeDash=alt.StrokeDash("series:N", title="구분 (실제/평균)"),
            tooltip=["class_name", "series", "captured_time:T", "detected_count:Q"],
        )
        .properties(height=380)
    )
    if domain is None and tick_values is None:
        chart = chart.interactive()
    st.altair_chart(apply_theme(chart), use_container_width=True)


def _render_time_series_chart(time_series) -> None:
    """피벗(촬영시각 × 장비) 시계열을 오버레이 차트와 같은 팔레트·축 스타일로 그린다.

    촬영시각이 희소하면(예: 두 지역 데이터가 하루씩 떨어져 있으면) 선만으로는 긴 공백을
    직선으로 이어 실제 추이처럼 오해되기 쉬우므로, 실제 데이터 지점마다 점을 함께 찍어
    어디가 실측이고 어디가 보간 구간인지 구분되게 한다(분석 현황 지역별 차트와 동일)."""
    if time_series.empty:
        st.info("해당 기간에 표시할 통계가 없습니다.")
        return
    data = time_series.reset_index().melt(
        "captured_time", var_name="class_name", value_name="detected_count"
    )
    chart = (
        alt.Chart(data)
        .mark_line(point=True)
        .encode(
            x=alt.X("captured_time:T", title="촬영시각"),
            y=alt.Y("detected_count:Q", title="탐지 수"),
            color=alt.Color("class_name:N", title="장비"),
            tooltip=["class_name", "captured_time:T", "detected_count:Q"],
        )
        .properties(height=380)
        .interactive()
    )
    st.altair_chart(apply_theme(chart), use_container_width=True)


def render_graph_column(
    start: datetime.datetime,
    end: datetime.datetime,
    region: str,
    equipment: Optional[List[str]],
    interval_label: str,
) -> None:
    """오른쪽 칸: 탐지 통계를 조회해 그래프를 제목 바로 아래 그리고, 그 아래 원본 표를 붙인다.
    기간 선택이 "1년"이면 실제 추이(실선)와 반월(보름) 단위 평균(점선)을, "24시간"이면 실제 추이와 2시간 단위 평균을
    한 그래프에 겹쳐 그린다."""
    with st.spinner("통계 조회 중..."):
        try:
            result = _cached_statistics(start, end)
        except Exception as exc:
            st.error(f"통계 조회 실패: {exc}")
            st.stop()

    if result is None:
        st.warning("해당 기간에 조회된 탐지 결과가 없습니다.")
        return

    render_section_header(
        "시간대별 탐지 추이",
        f"{start:%Y-%m-%d %H:%M}부터 {end:%Y-%m-%d %H:%M}까지",
        badge=interval_label,
    )
    selected_region = None if region == "전체" else region
    time_series = service.pivot_time_series(result.raw, selected_region, equipment)

    if interval_label == "1년":
        overlay_data = service.build_yearly_overlay(result.raw, start.year, selected_region, equipment)
        _render_actual_vs_average_chart(overlay_data, "해당 연도에 표시할 통계가 없습니다.")
    elif interval_label == "24시간":
        overlay_data = service.build_two_hour_overlay(result.raw, start, end, selected_region, equipment)
        two_hour_ticks = [
            (start + datetime.timedelta(hours=2 * i)).isoformat() for i in range(13)
        ]
        _render_actual_vs_average_chart(
            overlay_data,
            "해당 기간에 표시할 통계가 없습니다.",
            domain=[start.isoformat(), end.isoformat()],
            tick_values=two_hour_ticks,
        )
    else:
        _render_time_series_chart(time_series)

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
    with st.container(key="panel_statistics_report"):
        render_section_header(
            "통계 보고서",
            "분석관 의견을 포함한 HTML 통계 보고서를 생성합니다.",
            badge="REPORT",
        )
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
    """통계 페이지 전체를 그린다: 왼쪽 좁은 칸(장소 선택 + 조회 기간 + 장비 선택) + 오른쪽 넓은 칸(그래프, 제목 바로 아래)."""
    render_page_header(
        "탐지 통계",
        "기간·지역·위협등급·장비별 탐지 추이를 분석하고 통계 보고서를 생성합니다.",
        eyebrow="DETECTION ANALYTICS",
        status="통계 데이터 연결",
    )

    controls_col, graph_col = st.columns([1, 2.7], gap="large")

    with controls_col:
        with st.container(key="panel_statistics_filters"):
            render_section_header(
                "조회 조건",
                "장소·위협등급·장비와 분석 기간을 설정합니다.",
                badge="FILTER",
            )
            region = render_location_control()
            equipment = render_equipment_controls()
            start, end, interval_label = render_period_controls()


    with graph_col:
        with st.container(key="panel_statistics_graph"):
            render_graph_column(start, end, region, equipment, interval_label)
