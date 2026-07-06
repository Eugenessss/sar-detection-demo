"""
[프론트엔드 - 메인(홈) 페이지]
서비스에 처음 접속했을 때 보이는 소개 화면. 지금은 프로젝트 주제만 명시한다.
추론 등 세부 기능은 상단 메뉴의 다른 페이지에서 다룬다.
"""
import streamlit as st


def render_home_page() -> None:
    """프로젝트 이름과 주제를 보여주는 소개 페이지."""
    st.title("청출어람")
    st.subheader("EO/SAR 위성영상 기반 표적 후보 탐지 및 판독 지원 서비스")
    st.divider()
    st.caption("상단 메뉴에서 세부 기능을 확인할 수 있습니다.")
