import streamlit as st


def render_placeholder_page(title: str) -> None:
    st.title(title)
    st.info("아직 구현되지 않은 페이지입니다.")


def render_blank_1_page() -> None:
    render_placeholder_page("Blank 1")


def render_blank_2_page() -> None:
    render_placeholder_page("Blank 2")


def render_blank_3_page() -> None:
    render_placeholder_page("Blank 3")
