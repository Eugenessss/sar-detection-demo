"""역할별 상단 내비게이션.

streamlit-community-navigation-bar(서드파티, Streamlit<=1.58 고정 필요)는 안 쓴다 —
shared/tactical_map.py의 Custom Components v2(st.components.v2)가 Streamlit 1.59+를
요구해서 두 요구사항이 서로 충돌한다. 대신 Streamlit 네이티브 st.navigation(position="top")
위에 테마별 CSS만 얹는다. 아이콘(:material/name:)도 네이티브로 그대로 렌더링되므로
서드파티 navbar가 쓰던 아이콘 치환 CSS 트릭이 필요 없다.
"""

from pathlib import Path
from typing import Sequence

import streamlit as st

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "images"
_LOGO_PATHS = {
    "dark": _ASSETS_DIR / "cheongchuleoram-mark-dark.svg",
    "light": _ASSETS_DIR / "cheongchuleoram-mark.svg",
}

# 상단 내비게이션 자체는 app-{light,dark}.css가 안 건드리는 Streamlit 네이티브
# 헤더 영역([data-testid="stHeader"])이라 따로 테마별 색을 정의해둔다.
_NAV_COLORS = {
    "dark": {
        "header_bg": "#0d131a",
        "header_border": "#223040",
        "link": "#8fa3b6",
        "link_hover_bg": "#16202c",
        "link_hover": "#dbe6ec",
        "active_bg": "#16202c",
        "active": "#3ecfc0",
    },
    "light": {
        "header_bg": "#ffffff",
        "header_border": "#dce4ee",
        "link": "#475569",
        "link_hover_bg": "#f1f5f9",
        "link_hover": "#0f172a",
        "active_bg": "#eaf2ff",
        "active": "#1d4ed8",
    },
}


def _top_nav_css(theme: str) -> str:
    c = _NAV_COLORS.get(theme, _NAV_COLORS["dark"])
    return f"""
    <style>
    [data-testid="stHeader"] {{
        background: {c['header_bg']} !important;
        border-bottom: 1px solid {c['header_border']} !important;
    }}
    [data-testid="stTopNavLink"] {{
        border-radius: 8px !important;
    }}
    [data-testid="stTopNavLink"] span {{
        color: {c['link']} !important;
        font-weight: 600 !important;
    }}
    [data-testid="stTopNavLink"]:hover {{
        background: {c['link_hover_bg']} !important;
    }}
    [data-testid="stTopNavLink"]:hover span {{
        color: {c['link_hover']} !important;
    }}
    [data-testid="stTopNavLink"][aria-current="page"] {{
        background: {c['active_bg']} !important;
    }}
    [data-testid="stTopNavLink"][aria-current="page"] span {{
        color: {c['active']} !important;
        font-weight: 700 !important;
    }}
    [data-testid="stHeaderLogo"] img {{
        border-radius: 6px;
    }}
    </style>
    """


def render_top_navigation(pages: Sequence[object], theme: str = "dark"):
    """상단 내비게이션을 그리고 현재 선택된 StreamlitPage 객체를 반환한다.

    theme("dark"/"light")에 맞춰 헤더 배경·링크 색·로고를 함께 바꾼다 — 이 헤더는
    Streamlit 네이티브 영역이라 assets/css/app-{light,dark}.css가 못 건드린다.
    """
    st.html(_top_nav_css(theme))
    logo_path = _LOGO_PATHS.get(theme, _LOGO_PATHS["dark"])
    st.logo(str(logo_path), link=None)
    return st.navigation(list(pages), position="top")
