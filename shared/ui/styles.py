"""전역 스타일시트를 Streamlit 앱에 한 번 삽입한다.

라이트/다크 두 벌의 완전한 스타일시트(assets/css/app-light.css, app-dark.css)를
따로 두고, 어느 걸 넣을지만 Python에서 고른다. 두 파일이 같은 선택자 구조를
그대로 복제하고 있어(값만 다름) 컴포넌트별 CSS를 var(--ui-*) 토큰 하나로
묶는 것보다 안전하다 — 각 테마가 완전히 독립된, 이미 검증된 파일이라 서로
건드릴 일이 없다.
"""

from pathlib import Path
from typing import Literal

import streamlit as st

_CSS_DIR = Path(__file__).resolve().parents[2] / "assets" / "css"
_STYLESHEETS = {
    "dark": _CSS_DIR / "app-dark.css",
    "light": _CSS_DIR / "app-light.css",
}

Theme = Literal["dark", "light"]


def _read_stylesheet(theme: Theme) -> str:
    """개발 중 CSS 변경이 rerun에 즉시 반영되도록 매번 읽는다."""
    path = _STYLESHEETS.get(theme, _STYLESHEETS["dark"])
    return path.read_text(encoding="utf-8")


def load_global_styles(theme: Theme = "dark") -> None:
    """앱 공통 CSS를 로드한다."""
    st.html(f"<style>{_read_stylesheet(theme)}</style>")
