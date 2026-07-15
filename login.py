"""
[진입점 - 로그인]
app_user 테이블 기반 로그인 화면. app.py는 세션에 로그인 사용자가 없으면 이 화면만
보여주고 멈춘다. 로그인에 성공하면 세션에 사용자 정보(shared.auth.AuthUser)를 저장해,
app.py가 그 역할(분석관/지휘관)에 맞는 메뉴만 구성하도록 한다.
"""
import streamlit as st

from shared.auth import authenticate, create_session_token


def render_login_page() -> None:
    """아이디/비밀번호 입력 폼을 그리고, 성공하면 세션에 로그인 사용자를 저장한다."""
    with st.container(key="login_page"):
        hero_col, form_col = st.columns([1.18, 0.82], gap="large", vertical_alignment="center")

        with hero_col:
            st.html(
                """
                <section class="ui-login-hero">
                  <div class="ui-login-orbit" aria-hidden="true"></div>
                  <div class="ui-login-brand">
                    <span class="ui-login-brand-mark">◎</span>
                    <span>청출어람 위성정보 시스템</span>
                  </div>
                  <h1>더 빠르고 정확한<br><span>위성정보 판독</span></h1>
                  <p>
                    EO·SAR 영상과 탐지 결과, 변화 경보를 하나의 작전 화면에서 확인하고
                    분석관과 지휘관의 판단 흐름을 안전하게 연결합니다.
                  </p>
                  <div class="ui-login-features">
                    <span>EO/SAR 통합 판독</span>
                    <span>변화 탐지 경보</span>
                    <span>역할 기반 접근</span>
                    <span>지휘 결심 지원</span>
                  </div>
                </section>
                """
            )

        with form_col:
            with st.container(key="login_card"):
                st.html(
                    """
                    <header class="ui-login-card-heading">
                      <h2>시스템 로그인</h2>
                      <p>승인된 분석관 또는 지휘관 계정으로 접속해 주세요.</p>
                    </header>
                    """
                )

                with st.form("login_form"):
                    login_id = st.text_input(
                        "아이디",
                        placeholder="아이디를 입력하세요",
                        autocomplete="username",
                    )
                    password = st.text_input(
                        "비밀번호",
                        type="password",
                        placeholder="비밀번호를 입력하세요",
                        autocomplete="current-password",
                    )
                    submitted = st.form_submit_button(
                        "로그인",
                        type="primary",
                        icon=":material/login:",
                        use_container_width=True,
                    )

                st.html(
                    """
                    <div class="ui-security-note">
                      <span aria-hidden="true">🔒</span>
                      <span>본 시스템은 인가된 사용자만 사용할 수 있으며 접속 기록이 관리됩니다.</span>
                    </div>
                    """
                )

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
    # URL에 세션 토큰을 남겨둔다 -- 테마 전환 시 자동으로 걸리는 새로고침
    # (shared/theme_sync.py) 등 실제 브라우저 새로고침에도 로그인이 안 풀리게 하려면
    # st.session_state만으로는 부족하다 (새로고침 = 새 세션이라 session_state가
    # 비워짐). URL은 새로고침해도 그대로라, 토큰만 있으면 app.py가 복원한다.
    st.query_params["s"] = create_session_token(user)
    st.rerun()
