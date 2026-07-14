"""
[진입점 - 로그인]
app_user 테이블 기반 로그인 화면. app.py는 세션에 로그인 사용자가 없으면 이 화면만
보여주고 멈춘다. 로그인에 성공하면 세션에 사용자 정보(shared.auth.AuthUser)를 저장해,
app.py가 그 역할(분석관/지휘관)에 맞는 메뉴만 구성하도록 한다.
"""
import streamlit as st

from shared.auth import authenticate
from shared.ui_chrome import bracket_panel, render_command_bar


def render_login_page() -> None:
    """아이디/비밀번호 입력 폼을 그리고, 성공하면 세션에 로그인 사용자를 저장한다.

    화면 정중앙(가로+세로)에 좁은 폭으로 띄운다. stMainBlockContainer에 flex로
    세로 중앙정렬을 거는 방식은 Streamlit이 그 안쪽(#Main > block-container)의
    실제 높이/스크롤을 자체적으로 계산해서 밀어붙이는 바람에 !important를 걸어도
    카드가 위쪽에 붙어버렸다(실제 스크린샷으로 확인). 대신 패널 자체를
    position:fixed로 뷰포트 정중앙에 고정한다 — 부모 요소의 레이아웃 방식과
    무관하게 항상 먹히는 방식이라 더 확실하다. 로그인 페이지에서만 그려지는
    함수라, 이 스타일도 로그인 화면을 벗어나면(즉, 이 함수가 이번 실행에서 호출
    안 되면) 자동으로 같이 사라진다 — 다른 페이지의 레이아웃에는 영향이 없다.
    """
    st.html("""
    <style>
    .st-key-login_panel {
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        width: min(760px, 94vw) !important;
        padding: 2.1rem 2.4rem !important;
        z-index: 10;
    }
    </style>
    """)

    with bracket_panel("login_panel"):
        render_command_bar(
            "로그인", "분석관/지휘관 계정으로 로그인하면 역할에 맞는 화면으로 이동합니다.",
        )

        with st.form("login_form"):
            login_id = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", use_container_width=True)

        # 에러 메시지도 같은 패널 안에서 보여줘야 자연스러워서, return을 여기서
        # (bracket_panel의 with 블록 안에서) 바로 한다.
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
