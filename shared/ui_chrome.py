"""
[공용 - 관제 콘솔(C2) 디자인 장식]
.streamlit/config.toml의 다크 테마(색상·글꼴·각짐) 위에 얹는 순수 장식 요소.
실제 위젯의 위치·동작은 건드리지 않는다 — position:fixed 같은 트릭은 쓰지 않고,
Streamlit이 공식 지원하는 st.container(key=...) -> ".st-key-<key>" CSS 클래스만
타겟으로 한다 (참고: streamlit 패키지 내장 테마 스킬 문서의 권장 방식).

  render_command_bar()  : st.title() 대신 쓰는 페이지 상단 제목(브랜드+배지).
  bracket_panel()       : 모서리 브래킷 + 은은한 격자 배경이 있는 패널 컨테이너.
  apply_global_polish() : 버튼 호버 발광 등 자잘한 상호작용 강조 (앱 진입점에서 한 번).

색상 값은 .streamlit/config.toml의 팔레트와 맞춰져 있다. 팔레트를 바꾸면 두 곳 다
같이 고쳐야 한다 (Streamlit 테마 CSS 변수명이 버전마다 달라질 수 있어 값을 직접 박아
넣는 쪽을 택했다).
"""
import contextlib
from typing import Iterator

import streamlit as st

_ACCENT = "#3ecfc0"
_BORDER = "#223040"
_TEXT = "#dbe6ec"
_FAINT = "#46586a"


def render_command_bar(title: str, subtitle: str = "", badge: str = "TRAINING SYS") -> None:
    """페이지 맨 위 제목을 커맨드바 스타일(브랜드 라벨 + 배지)로 그린다. st.title() 대체."""
    st.html(f"""
    <div style="display:flex;align-items:center;gap:0.7rem;
                padding-bottom:0.55rem;margin-bottom:0.8rem;
                border-bottom:1px solid {_BORDER};">
      <div style="line-height:1.15;">
        <div style="font-size:0.6rem;letter-spacing:0.22em;color:{_FAINT};
                    text-transform:uppercase;">청출어람</div>
        <div style="font-size:1.15rem;font-weight:700;letter-spacing:0.02em;
                    color:{_TEXT};">{title}</div>
      </div>
      <span style="font-size:0.58rem;letter-spacing:0.12em;font-weight:700;
                   padding:0.2rem 0.5rem;border:1px solid {_ACCENT}66;
                   color:{_ACCENT};background:{_ACCENT}14;
                   text-transform:uppercase;">{badge}</span>
    </div>
    """)
    if subtitle:
        st.caption(subtitle)


@contextlib.contextmanager
def bracket_panel(key: str) -> Iterator[None]:
    """모서리 브래킷 + 은은한 격자 배경이 있는 패널 컨테이너.

    with 블록 안에 평소처럼 위젯을 넣으면 된다. 격자는 실제 배경(background-image)
    이라 지도 컴포넌트(iframe)처럼 위에 다른 요소가 덮이는 영역에는 안 보이고,
    패널의 빈 여백에만 보인다 — 지도 위에 뭔가를 억지로 겹치지 않아 안전하다.
    key는 컨테이너마다 고유해야 한다(같은 key를 두 번 쓰면 충돌).
    """
    with st.container(border=True, key=key):
        yield

    st.html(f"""
    <style>
    .st-key-{key} {{
        position: relative;
        background-image:
            linear-gradient({_ACCENT}14 1px, transparent 1px),
            linear-gradient(90deg, {_ACCENT}14 1px, transparent 1px);
        background-size: 36px 36px;
    }}
    .st-key-{key}::before {{
        content: "";
        position: absolute;
        top: -1px; left: -1px;
        width: 16px; height: 16px;
        border: 2px solid {_ACCENT};
        border-right: none; border-bottom: none;
        opacity: 0.65;
        pointer-events: none;
    }}
    .st-key-{key}::after {{
        content: "";
        position: absolute;
        bottom: -1px; right: -1px;
        width: 16px; height: 16px;
        border: 2px solid {_ACCENT};
        border-left: none; border-top: none;
        opacity: 0.65;
        pointer-events: none;
    }}
    </style>
    """)


def apply_global_polish() -> None:
    """버튼류에 호버 시 은은한 발광 테두리를 준다. 위치·크기는 안 건드리고 색상/그림자만
    바꾸는 순수 장식이라, 앱 진입점(app.py)에서 로그인 여부와 상관없이 한 번 불러도 된다.
    data-testid는 Streamlit이 공식 문서화한 안정적인 선택자만 쓴다.
    """
    st.html(f"""
    <style>
    [data-testid="stButton"] button,
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stDownloadButton"] button {{
        transition: box-shadow 150ms ease, border-color 150ms ease;
    }}
    [data-testid="stButton"] button:hover,
    [data-testid="stFormSubmitButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover {{
        border-color: {_ACCENT} !important;
        box-shadow: 0 0 10px {_ACCENT}59;
    }}
    </style>
    """)
