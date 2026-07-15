"""전역 스타일시트를 Streamlit 앱에 한 번 삽입한다."""

from pathlib import Path

import streamlit as st

_STYLESHEET = Path(__file__).resolve().parents[2] / "assets" / "css" / "app.css"


@st.cache_data(show_spinner=False)
def _read_stylesheet(mtime: float) -> str:
    """CSS 파일을 읽어 캐시한다.

    파일 수정시각(mtime)을 캐시 키로 받아, 파일이 바뀌면 키가 달라져 자동으로 다시
    읽는다 — 개발 중 hot-reload는 그대로 유지하면서, rerun마다 디스크에서 전체 CSS를
    다시 읽던 낭비만 없앤다. (mtime 값 자체는 본문에서 쓰지 않고 캐시 구분용으로만 쓴다.)"""
    return _STYLESHEET.read_text(encoding="utf-8")


def load_global_styles() -> None:
    """앱 공통 CSS를 로드한다."""
    st.html(f"<style>{_read_stylesheet(_STYLESHEET.stat().st_mtime)}</style>")
