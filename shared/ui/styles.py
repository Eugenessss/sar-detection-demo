"""전역 스타일시트를 Streamlit 앱에 한 번 삽입한다."""

from pathlib import Path

import streamlit as st

_STYLESHEET = Path(__file__).resolve().parents[2] / "assets" / "css" / "app.css"


def _read_stylesheet() -> str:
    """개발 중 CSS 변경이 rerun에 즉시 반영되도록 매번 읽는다."""
    return _STYLESHEET.read_text(encoding="utf-8")


def load_global_styles() -> None:
    """앱 공통 CSS를 로드한다."""
    st.html(f"<style>{_read_stylesheet()}</style>")
