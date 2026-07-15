"""
[진입점 - 로그인]
app_user 테이블 기반 로그인 화면. app.py는 세션에 로그인 사용자가 없으면 이 화면만
보여주고 멈춘다. 로그인에 성공하면 세션에 사용자 정보(shared.auth.AuthUser)를 저장해,
app.py가 그 역할(분석관/지휘관)에 맞는 메뉴만 구성하도록 한다.
"""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

from shared.auth import authenticate

_ASSETS = Path(__file__).resolve().parent / "assets" / "images"
# 다크 배경용 ARGOS 로고(흰 락업, 여백 트림 + 배경 투명). 위성 야간 배경 위에 박스 없이 얹힌다.
_LOGO_PATH = _ASSETS / "argos_logo_wide_ondark.png"
# 로그인 배경(야간 위성사진 톤). 실제 위성 사진으로 바꾸려면 이 파일만 교체하면 된다
# (SVG 대신 JPG/PNG를 쓰면 아래 _bg_data_uri의 MIME 타입만 맞춰주면 됨).
_LOGIN_BG_PATH = _ASSETS / "login-bg.svg"


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    """ARGOS 로고 PNG를 <img>에 바로 넣을 수 있는 data URI로 만든다 (프로세스당 1회)."""
    return "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")


@lru_cache(maxsize=1)
def _bg_data_uri() -> str:
    """로그인 배경 SVG를 CSS url()에 바로 넣을 data URI로 만든다 (프로세스당 1회)."""
    return "data:image/svg+xml;base64," + base64.b64encode(_LOGIN_BG_PATH.read_bytes()).decode("ascii")


def render_login_page() -> None:
    """아이디/비밀번호 입력 폼을 그리고, 성공하면 세션에 로그인 사용자를 저장한다."""
    with st.container(key="login_page"):
        # 화면 전체를 덮는 야간 위성 배경 레이어(어두운 오버레이는 CSS ::after가 얹는다).
        st.html(
            f'<div class="ui-login-bg" aria-hidden="true" '
            f"style=\"background-image:url('{_bg_data_uri()}')\"></div>"
        )

        hero_col, form_col = st.columns([1, 1], gap="small")

        with hero_col:
            st.html(
                f"""
                <section class="ui-login-hero">
                  <img class="ui-login-logo" src="{_logo_data_uri()}" alt="ARGOS">
                  <div class="ui-login-eyebrow">청출어람 위성정보 시스템</div>
                  <h1>EO/SAR 영상 분석<br><span>ARGOS</span></h1>
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
                    f"""
                    <header class="ui-login-card-heading">
                      <img class="ui-login-card-logo" src="{_logo_data_uri()}" alt="ARGOS">
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

                # 로그인 페이지 컨테이너가 화면 전체를 덮는 고정 레이어이므로,
                # 실패 메시지는 반드시 카드 안(폼 바로 아래)에서 그려야 보인다.
                if submitted:
                    _process_login(login_id, password)

                st.html(
                    """
                    <div class="ui-security-note">
                      <span aria-hidden="true">🔒</span>
                      <span>본 시스템은 인가된 사용자만 사용할 수 있으며 접속 기록이 관리됩니다.</span>
                    </div>
                    """
                )


def _process_login(login_id: str, password: str) -> None:
    """자격 증명을 검증해 실패 사유를 표시하고, 성공하면 세션을 갱신한다."""
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
