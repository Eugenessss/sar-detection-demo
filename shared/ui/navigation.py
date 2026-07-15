"""역할별 상단 내비게이션과 사용자 계정 영역."""

import json
from html import escape
from pathlib import Path
from typing import Sequence

import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
from streamlit_navigation_bar import st_navbar

# ARGOS 로고 원본은 PNG(argos_logo_small.png)인데, navbar 라이브러리가 SVG 텍스트만
# 받으므로(image/svg+xml 하드코딩) PNG를 base64로 내장한 래퍼 SVG를 사용한다.
_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "images" / "argos-logo.svg"
_LOGO_PAGE_TITLE = "청출어람 홈"

# navbar 프런트엔드는 마지막 클릭 값을 이후 리런에 위젯 상태로 재전송한다. 위젯 키를
# 페이지별로 분리하면(위젯 ID가 키에 따라 달라짐) 다른 페이지에서 클릭한 옛 값이 현재
# 페이지의 navbar에 매칭되지 않아 "숨김 페이지에서 버튼을 누르면 예전 메뉴로 튕기는"
# 유령 내비게이션이 차단된다. 그래도 새어 들어오는 값은 클릭 기록(_SEEN)으로 거른다.
_NAV_WIDGET_KEY_PREFIX = "primary_navigation"
_SEEN_NAV_CLICKS_KEY = "_navbar_seen_click_values"
_REROUTE_GUARD_KEY = "_navbar_reroute_in_flight"

_NAVBAR_STYLES = {
    "nav": {
        "background-color": "#FFFFFF",
        "border-bottom": "1px solid #DCE4EE",
        "box-shadow": "0 8px 28px rgba(15, 23, 42, 0.07)",
        "height": "72px",
        "padding": "0 24px",
    },
    "div": {
        "max-width": "none",
    },
    "ul": {
        "gap": "6px",
    },
    "img": {
        "height": "42px",
        "width": "42px",
    },
    "span": {
        "color": "#475569",
        "font-family": "Pretendard, Noto Sans KR, sans-serif",
        "font-size": "14px",
        "font-weight": "600",
        "letter-spacing": "-0.01em",
        "padding": "10px 15px",
        "border-radius": "11px",
    },
    "active": {
        "color": "#173B67",
        "background-color": "#EAF2FF",
        "font-weight": "700",
    },
    "hover": {
        "color": "#173B67",
        "background-color": "#F1F5F9",
    },
}

_NAVBAR_OPTIONS = {
    "show_menu": False,
    "show_sidebar": False,
    "hide_nav": True,
    "fix_shadow": True,
    "use_padding": True,
    "sidebar_under_navbar": False,
}


def _role_label(role: str) -> str:
    return "지휘관" if role == "COMMANDER" else "영상판독관"


def _component_css(
    auth_user,
    hidden_pages: Sequence[object],
    navigation_pages: Sequence[object],
) -> str:
    """navbar iframe 안에 적용할 사용자 영역·숨김 페이지 CSS를 만든다."""
    account_text = f"{auth_user.user_name or auth_user.login_id} · {_role_label(auth_user.role)}"
    safe_account_text = (
        json.dumps(account_text, ensure_ascii=False)
        .replace("<", "\\003C ")
        .replace(">", "\\003E ")
    )

    hidden_selectors = ",\n".join(
        f'.navbar-right li:has(.navbar-span[data-text="{escape(page.title)}"])'
        for page in hidden_pages
    )
    hidden_rule = f"{hidden_selectors} {{ display: none !important; }}" if hidden_selectors else ""

    # st.Page의 Material 아이콘 표기(:material/name:)를 community navbar가
    # 그대로 출력하는 호환성 문제를 CSS 아이콘으로 대체한다.
    icon_rules = []
    for page in navigation_pages:
        icon = getattr(page, "icon", None)
        if not isinstance(icon, str) or not icon.startswith(":material/"):
            continue
        icon_name = icon.removeprefix(":material/").removesuffix(":")
        title = escape(page.title)
        icon_rules.append(
            f"""
            .navbar-span[data-text="{title}"] > .navbar-icon {{
              display: none !important;
            }}
            .navbar-span[data-text="{title}"]::before {{
              margin-right: 7px;
              content: "{icon_name}";
              font-family: "Material Icons";
              font-size: 19px;
              font-weight: 400;
              vertical-align: -3px;
            }}
            """
        )
    icon_rule = "\n".join(icon_rules)

    return f"""
    .navbar-left {{
      flex: 1 1 auto !important;
      width: auto !important;
    }}
    .navbar-right {{
      flex: 0 0 auto !important;
      width: auto !important;
    }}
    .navbar-left > .navbar-list {{
      justify-content: flex-start !important;
    }}
    .navbar-right > .navbar-list {{
      justify-content: flex-end !important;
      align-items: center !important;
      white-space: nowrap;
    }}
    .navbar-left .navbar-item:first-child {{
      margin-right: 12px;
    }}
    .navbar-left .navbar-item:first-child::after {{
      margin-left: 10px;
      color: #173B67;
      content: "청출어람";
      font-size: 15px;
      font-weight: 800;
      letter-spacing: -0.035em;
    }}
    .navbar-right > .navbar-list::before {{
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      margin-right: 4px;
      padding: 0 12px;
      border: 1px solid #DCE4EE;
      border-radius: 11px;
      color: #475569;
      background: #F8FAFC;
      content: {safe_account_text};
      font-family: Pretendard, "Noto Sans KR", sans-serif;
      font-size: 12px;
      font-weight: 700;
    }}
    .navbar-right li:has(.navbar-span[data-text="로그아웃"]) .navbar-span {{
      border: 1px solid #DCE4EE;
      color: #64748B;
      background: #FFFFFF;
      font-size: 12px !important;
    }}
    .navbar-right li:has(.navbar-span[data-text="로그아웃"]) .navbar-span:hover {{
      border-color: #FECACA;
      color: #DC2626 !important;
      background: #FFF7F7 !important;
    }}
    {hidden_rule}
    {icon_rule}
    @media (max-width: 980px) {{
      .navbar-left .navbar-item:first-child::after,
      .navbar-right > .navbar-list::before {{ display: none; }}
      nav.navbar {{ padding-inline: 12px !important; }}
    }}
    """


def _consume_nav_click(nav_widget_key: str) -> bool:
    """이번 리런이 navbar를 실제로 클릭해서 생긴 것인지 판정한다.

    allow_reselect=True 덕에 클릭 값은 (페이지, 클릭시각 ms)라 매 클릭이 유일하다.
    처음 보는 값이면 진짜 클릭으로 기록하고 True, 이미 처리한 값의 재전송이면 False.
    """
    raw_value = st.session_state.get(nav_widget_key)
    if raw_value is None:
        return False
    marker = tuple(raw_value) if isinstance(raw_value, (list, tuple)) else (raw_value,)
    seen = st.session_state.setdefault(_SEEN_NAV_CLICKS_KEY, [])
    if marker in seen:
        return False
    seen.append(marker)
    return True


def _intended_router_page(navigation_pages: Sequence[object]):
    """이번 리런이 향하던 페이지(위젯 리런이면 현재 화면의 페이지)를 찾는다.

    리런 요청에는 페이지 스크립트 해시나 URL 경로 이름 중 하나만 실려 올 수 있어
    둘 다 확인한다 (위젯 리런은 보통 URL 경로 이름으로 온다).
    """
    ctx = get_script_run_ctx()
    if ctx is None:
        return None
    intended_hash = ctx.pages_manager.intended_page_script_hash
    intended_name = ctx.pages_manager.intended_page_name
    for page in navigation_pages:
        if intended_hash and getattr(page, "_script_hash", None) == intended_hash:
            return page
        if intended_name and getattr(page, "url_path", None) == intended_name:
            return page
    return None


def render_top_navigation(
    visible_pages: Sequence[object],
    hidden_pages: Sequence[object],
    logout_page: object,
    auth_user,
):
    """상단 메뉴를 그리고 현재 선택된 StreamlitPage 객체를 반환한다."""
    navigation_pages = [*visible_pages, logout_page, *hidden_pages]

    # 위젯 키를 "지금 향하는 페이지"별로 분리한다. 로그인 직후처럼 페이지를 알 수
    # 없으면 default 키를 쓴다 (navbar가 기본 페이지로 안내하고 다음 리런부터 정상).
    intended_page = _intended_router_page(navigation_pages)
    nav_widget_key = (
        f"{_NAV_WIDGET_KEY_PREFIX}_{getattr(intended_page, 'url_path', None) or 'default'}"
    )

    current_page = st_navbar(
        pages=list(visible_pages),
        right=[logout_page, *hidden_pages],
        logo_path=str(_LOGO_PATH),
        logo_page=_LOGO_PAGE_TITLE,
        styles=_NAVBAR_STYLES,
        css=_component_css(auth_user, hidden_pages, navigation_pages),
        options=_NAVBAR_OPTIONS,
        adjust=True,
        set_path=True,
        # 클릭마다 새 타임스탬프가 붙은 값을 받게 해, 과거 클릭 값의 재전송과
        # 실제 클릭을 _consume_nav_click()에서 구분할 수 있게 한다.
        allow_reselect=True,
        key=nav_widget_key,
    )

    # navbar를 클릭하지 않은 리런(페이지 안 버튼 등)에서는 navbar 반환값이 과거
    # 클릭의 잔상일 수 있다. 그 경우 이번 리런이 향하던 페이지를 그대로 유지한다.
    # (예: 숨김 페이지인 상세 통계에서 필터를 누르면 분석 현황으로 튕기던 버그)
    rerouted_last_run = st.session_state.pop(_REROUTE_GUARD_KEY, False)
    if not _consume_nav_click(nav_widget_key):
        if intended_page is not None:
            mismatch = (
                isinstance(current_page, str)
                or current_page._script_hash != intended_page._script_hash
            )
            if not mismatch:
                return current_page
            if not rerouted_last_run:
                # navbar가 이미 라우터를 엉뚱한 페이지로 잡아뒀으므로 공식 전환
                # API로 의도한 페이지로 되돌린다(리런 1회 추가). 쿼리 파라미터는
                # 경보 상세(alert_id) 같은 화면이 쓰므로 그대로 보존한다.
                st.session_state[_REROUTE_GUARD_KEY] = True
                st.switch_page(intended_page, query_params=st.query_params.to_dict())
            # 직전 리런에서 보정했는데도 다시 어긋나면(비정상 상황) 무한 루프를
            # 피하기 위해 navbar 판정을 그대로 따른다.

    # navbar 로고는 라이브러리 내부의 가상 페이지이므로 문자열을 반환한다.
    # 이때 페이지 객체를 직접 실행하면 Streamlit이 차단하므로 공식 전환 API를 쓴다.
    if isinstance(current_page, str):
        if current_page == _LOGO_PAGE_TITLE:
            st.switch_page(visible_pages[0])
            st.stop()

        pages_by_title = {page.title: page for page in navigation_pages}
        if current_page in pages_by_title:
            st.switch_page(pages_by_title[current_page])
            st.stop()

        raise RuntimeError(f"알 수 없는 내비게이션 페이지입니다: {current_page}")

    return current_page
