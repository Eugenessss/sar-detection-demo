"""역할별 상단 내비게이션과 사용자 계정 영역."""

import json
from html import escape
from pathlib import Path
from typing import Sequence

import streamlit as st
from streamlit_navigation_bar import st_navbar

# ARGOS 로고 원본은 PNG(argos_logo_small.png)인데, navbar 라이브러리가 SVG 텍스트만
# 받으므로(image/svg+xml 하드코딩) PNG를 base64로 내장한 래퍼 SVG를 사용한다.
_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "images" / "argos-logo.svg"
_LOGO_PAGE_TITLE = "청출어람 홈"

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


def render_top_navigation(
    visible_pages: Sequence[object],
    hidden_pages: Sequence[object],
    logout_page: object,
    auth_user,
):
    """상단 메뉴를 그리고 현재 선택된 StreamlitPage 객체를 반환한다."""
    navigation_pages = [*visible_pages, logout_page, *hidden_pages]
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
        key="primary_navigation_v2",
    )

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
