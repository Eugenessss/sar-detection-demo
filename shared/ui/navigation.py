"""역할별 상단 내비게이션.

streamlit-community-navigation-bar(서드파티, Streamlit<=1.58 고정 필요)는 안 쓴다 —
shared/tactical_map.py의 Custom Components v2(st.components.v2)가 Streamlit 1.59+를
요구해서 두 요구사항이 서로 충돌한다. 대신 Streamlit 네이티브 st.navigation(position="top")
위에 다크 테마 CSS만 얹는다. 아이콘(:material/name:)도 네이티브로 그대로 렌더링되므로
서드파티 navbar가 쓰던 아이콘 치환 CSS 트릭이 필요 없다.
"""

from pathlib import Path
from typing import Sequence

import streamlit as st

_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "images" / "cheongchuleoram-mark-dark.svg"

_TOP_NAV_CSS = """
<style>
[data-testid="stHeader"] {
    background: #0d131a !important;
    border-bottom: 1px solid #223040 !important;
}
[data-testid="stTopNavLink"] {
    border-radius: 8px !important;
}
[data-testid="stTopNavLink"] span {
    color: #8fa3b6 !important;
    font-weight: 600 !important;
}
[data-testid="stTopNavLink"]:hover {
    background: #16202c !important;
}
[data-testid="stTopNavLink"]:hover span {
    color: #dbe6ec !important;
}
[data-testid="stTopNavLink"][aria-current="page"] {
    background: #16202c !important;
}
[data-testid="stTopNavLink"][aria-current="page"] span {
    color: #3ecfc0 !important;
    font-weight: 700 !important;
}
[data-testid="stHeaderLogo"] img {
    border-radius: 6px;
}
</style>
"""


def apply_top_nav_style() -> None:
    st.html(_TOP_NAV_CSS)


def render_top_navigation(pages: Sequence[object]):
    """상단 내비게이션을 그리고 현재 선택된 StreamlitPage 객체를 반환한다."""
    apply_top_nav_style()
    st.logo(str(_LOGO_PATH), link=None)
    return st.navigation(list(pages), position="top")
