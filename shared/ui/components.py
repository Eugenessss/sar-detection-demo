"""HTML/CSS 기반의 재사용 가능한 표현용 UI 컴포넌트."""

from dataclasses import dataclass
from html import escape
from typing import Iterable, Optional

import streamlit as st


@dataclass(frozen=True)
class MetricItem:
    label: str
    value: str
    detail: str = ""
    tone: str = "primary"


@dataclass(frozen=True)
class InfoItem:
    """작업 대상·센서·시각처럼 짧은 문맥 정보를 표시하는 항목."""

    label: str
    value: str
    tone: str = "default"


def render_page_header(
    title: str,
    description: str,
    *,
    eyebrow: str = "OPERATIONAL INTELLIGENCE",
    status: Optional[str] = None,
) -> None:
    """페이지 상단의 제목·설명·상태를 일관된 형태로 표시한다."""
    status_html = ""
    if status:
        status_html = (
            '<span class="ui-page-status">'
            '<span class="ui-status-dot"></span>'
            f"{escape(status)}</span>"
        )

    st.html(
        f"""
        <section class="ui-page-header">
          <div>
            <div class="ui-eyebrow">{escape(eyebrow)}</div>
            <h1>{escape(title)}</h1>
            <p>{escape(description)}</p>
          </div>
          {status_html}
        </section>
        """
    )


def render_metric_grid(items: Iterable[MetricItem]) -> None:
    """같은 폭의 KPI 카드 묶음을 표시한다."""
    metric_items = list(items)
    if not metric_items:
        return

    columns = st.columns(len(metric_items), gap="medium")
    for column, item in zip(columns, metric_items):
        with column:
            st.html(
                f"""
                <article class="ui-metric-card ui-tone-{escape(item.tone)}">
                  <div class="ui-metric-label">{escape(item.label)}</div>
                  <div class="ui-metric-value">{escape(item.value)}</div>
                  <div class="ui-metric-detail">{escape(item.detail) or '&nbsp;'}</div>
                </article>
                """
            )


def render_info_strip(items: Iterable[InfoItem], *, compact: bool = False) -> None:
    """선택된 영상이나 조회 조건을 한 줄 메타정보 스트립으로 표시한다."""
    info_items = list(items)
    if not info_items:
        return

    item_html = "".join(
        f"""
        <div class="ui-info-item ui-info-{escape(item.tone)}">
          <span>{escape(item.label)}</span>
          <strong>{escape(item.value)}</strong>
        </div>
        """
        for item in info_items
    )
    compact_class = " ui-info-strip-compact" if compact else ""
    st.html(f'<div class="ui-info-strip{compact_class}">{item_html}</div>')


def render_empty_state(
    title: str,
    description: str,
    *,
    symbol: str = "◇",
) -> None:
    """데이터·영상이 아직 없는 패널에 공통 빈 상태를 표시한다."""
    st.html(
        f"""
        <div class="ui-empty-state">
          <div class="ui-empty-symbol" aria-hidden="true">{escape(symbol)}</div>
          <strong>{escape(title)}</strong>
          <p>{escape(description)}</p>
        </div>
        """
    )


def render_section_header(
    title: str,
    description: str = "",
    *,
    badge: Optional[str] = None,
) -> None:
    """지도·그래프·목록 카드 내부의 제목 행을 표시한다."""
    badge_html = f'<span class="ui-section-badge">{escape(badge)}</span>' if badge else ""
    description_html = f"<p>{escape(description)}</p>" if description else ""
    st.html(
        f"""
        <header class="ui-section-header">
          <div>
            <h2>{escape(title)}</h2>
            {description_html}
          </div>
          {badge_html}
        </header>
        """
    )
