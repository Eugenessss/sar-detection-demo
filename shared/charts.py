"""Altair 차트 공통 스타일 — 모든 페이지의 그래프가 같은 팔레트와 축·범례 톤을 쓴다."""

import altair as alt

# .streamlit/config.toml의 chartCategoricalColors와 같은 값. Streamlit 내장 차트와
# Altair 차트가 서로 다른 기본 팔레트를 쓰는 것을 막는다.
CATEGORY_PALETTE = ["#2563EB", "#0EA5E9", "#059669", "#D97706", "#DC2626", "#7C3AED"]


def apply_theme(chart: alt.Chart) -> alt.Chart:
    """축·범례·카테고리 팔레트 공통 스타일을 최상위 차트에 적용한다.

    configure_*는 차트 조립(encode/properties/interactive)이 끝난 뒤 마지막에
    한 번만 호출할 수 있으므로, 각 화면은 완성된 차트를 이 함수에 통과시킨다.
    """
    return (
        chart.configure_view(strokeOpacity=0)
        .configure_axis(
            gridColor="#E7EDF4",
            domainColor="#CBD5E1",
            labelColor="#64748B",
            titleColor="#334155",
            tickColor="#CBD5E1",
        )
        .configure_legend(labelColor="#475569", titleColor="#334155", orient="bottom")
        .configure_range(category=CATEGORY_PALETTE)
    )
