"""
[빈 페이지]
상단 메뉴의 Blank 1~3 자리를 채우는 임시 페이지. 아직 기능이 없고
"준비 중" 안내만 보여준다. 나중에 새 화면을 만들 때 여기 함수를 실제 내용으로 교체하면 된다.
"""
import streamlit as st


def render_placeholder_page(title: str) -> None:
    """제목과 '아직 구현되지 않음' 안내만 보여주는 공통 빈 페이지."""
    st.title(title)
    st.info("아직 구현되지 않은 페이지입니다.")


def render_blank_1_page() -> None:
    """Blank 1 페이지를 그린다."""
    render_placeholder_page("Blank 1")


def render_blank_2_page() -> None:
    """Blank 2 페이지를 그린다."""
    render_placeholder_page("Blank 2")


def render_blank_3_page() -> None:
    """Blank 3 페이지를 그린다."""
    render_placeholder_page("Blank 3")
