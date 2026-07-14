"""
[진입점 - 로그인]
app_user 테이블 기반 로그인 화면. app.py는 세션에 로그인 사용자가 없으면 이 화면만
보여주고 멈춘다. 로그인에 성공하면 세션에 사용자 정보(shared.auth.AuthUser)를 저장해,
app.py가 그 역할(분석관/지휘관)에 맞는 메뉴만 구성하도록 한다.
"""
import streamlit as st

from shared.auth import authenticate


def render_login_page() -> None:
    """아이디/비밀번호 입력 폼을 그리고, 성공하면 세션에 로그인 사용자를 저장한다."""
    st.title("청출어람 로그인")
    st.caption("분석관/지휘관 계정으로 로그인하면 역할에 맞는 화면으로 이동합니다.")

    with st.form("login_form"):
        login_id = st.text_input("아이디")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인", use_container_width=True)

    if not submitted:
        return

    try:
        user = authenticate(login_id, password)
    except Exception as exc:
        st.error(f"로그인 처리 중 오류가 발생했습니다: {exc}")
        return

    if user is None:
        st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
        return

    st.session_state["auth_user"] = user
    st.rerun()
