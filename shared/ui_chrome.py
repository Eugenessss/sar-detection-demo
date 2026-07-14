"""
[공용 - 관제 콘솔(C2) 디자인 장식]
.streamlit/config.toml의 다크 테마(색상·글꼴·각짐) 위에 얹는 순수 장식 요소.
실제 위젯의 위치·동작은 건드리지 않는다 — position:fixed 같은 트릭은 쓰지 않고,
Streamlit이 공식 지원하는 st.container(key=...) -> ".st-key-<key>" CSS 클래스만
타겟으로 한다 (참고: streamlit 패키지 내장 테마 스킬 문서의 권장 방식).

  render_command_bar()  : st.title() 대신 쓰는 페이지 상단 제목(브랜드+배지+아이콘+사용자정보).
  bracket_panel()       : 모서리 브래킷 + 은은한 격자 배경이 있는 패널 컨테이너.
  floating_box()        : bracket_panel() 안에서 우상단에 떠 있는 작은 정보 박스
                           (지도 위 범례 등). bracket_panel()의 with 블록 "안"에서만 쓴다
                           (그 패널의 position:relative를 기준으로 떠야 하므로).
  apply_global_polish() : 버튼 호버 발광 등 자잘한 상호작용 강조 (앱 진입점에서 한 번).
  apply_icon_rail_nav() : 사이드바 내비게이션을 아이콘만 보이는 좁은 레일로 만든다.

apply_icon_rail_nav()이 쓰는 data-testid(stSidebar, stSidebarNavLink 등)는 Streamlit이
문서에 공개하진 않지만, 실제 프론트엔드 번들(streamlit/static/static/js/*.js)에서 문자열
그대로 검색해 확인한 값이다 — 이 정도는 배포판마다 고정된 빌드 산출물이라 이 버전에서는
안정적이지만, Streamlit을 업그레이드하면 값이 바뀌어 이 함수만 조용히 무효화될 수 있다
(에러는 안 나고 그냥 스타일이 안 먹는 정도).

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
_PANEL = "#10161d"

# 커맨드바에 쓰는 작은 장식용 아이콘 3개 (기능 없음 — 관제 콘솔 톤을 위한 순수 장식).
_ICON_GRID = (
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" '
    'stroke-width="1.6"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" '
    'width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>'
    '<rect x="14" y="14" width="7" height="7"/></svg>'
)
_ICON_LAYERS = (
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" '
    'stroke-width="1.6"><polygon points="12 2 2 7 12 12 22 7 12 2"/>'
    '<polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>'
)
_ICON_STAR = (
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" '
    'stroke-width="1.6"><polygon points="12 2 15 9 22 9.5 17 14.5 18.5 22 12 18 5.5 22 '
    '7 14.5 2 9.5 9 9 12 2"/></svg>'
)


def render_command_bar(title: str, subtitle: str = "", badge: str = "TRAINING SYS") -> None:
    """페이지 맨 위 제목을 커맨드바 스타일(브랜드+배지+장식 아이콘+사용자/시각)로 그린다.

    st.title() 대체. 로그인 상태면(shared.auth.AuthUser가 세션에 있으면) 오른쪽에
    로그인한 사람과 역할을 실제 값으로 보여준다 (꾸며낸 값 없음).
    """
    auth_user = st.session_state.get("auth_user")
    right_html = ""
    if auth_user is not None:
        right_html = (
            f'<div style="font-size:0.62rem;color:{_FAINT};letter-spacing:0.04em;'
            f'text-align:right;white-space:nowrap;">'
            f'USER&nbsp;<span style="color:{_TEXT};">{auth_user.user_name}</span>'
            f'&nbsp;·&nbsp;{auth_user.role}</div>'
        )

    st.html(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;
                padding-bottom:0.55rem;margin-bottom:0.8rem;
                border-bottom:1px solid {_BORDER};">
      <div style="display:flex;align-items:center;gap:0.85rem;min-width:0;">
        <div style="line-height:1.15;">
          <div style="font-size:0.6rem;letter-spacing:0.22em;color:{_FAINT};
                      text-transform:uppercase;">청출어람</div>
          <div style="font-size:1.15rem;font-weight:700;letter-spacing:0.02em;
                      color:{_TEXT};white-space:nowrap;">{title}</div>
        </div>
        <span style="font-size:0.58rem;letter-spacing:0.12em;font-weight:700;
                     padding:0.2rem 0.5rem;border:1px solid {_ACCENT}66;
                     color:{_ACCENT};background:{_ACCENT}14;
                     text-transform:uppercase;white-space:nowrap;">{badge}</span>
        <span style="display:flex;align-items:center;gap:0.55rem;color:{_FAINT};">
          {_ICON_GRID}{_ICON_LAYERS}{_ICON_STAR}
        </span>
      </div>
      {right_html}
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


@contextlib.contextmanager
def floating_box(
    key: str, top: str = "0.75rem", right: str = "0.75rem", width: str = "230px",
) -> Iterator[None]:
    """bracket_panel() 안에서 오른쪽 위에 떠 있는 작은 정보 박스를 그린다 (지도 위 범례 등).

    bracket_panel()이 이미 position:relative를 걸어둔 컨테이너 "안"에서 호출해야
    한다 — 그 패널을 기준으로 절대 위치를 잡기 때문. absolute라 일반 흐름에서
    빠지므로, 앞뒤 다른 위젯의 배치에는 영향을 주지 않는다.
    """
    with st.container(border=True, key=key):
        yield

    st.html(f"""
    <style>
    .st-key-{key} {{
        position: absolute;
        top: {top};
        right: {right};
        width: {width};
        z-index: 20;
        background: {_PANEL}f0;
        backdrop-filter: blur(3px);
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


def apply_icon_rail_nav() -> None:
    """왼쪽 사이드바 페이지 내비게이션의 글자 라벨을 숨기고 폭을 좁혀 아이콘 레일로 만든다.

    st.navigation(position="sidebar")로 등록한 페이지마다 icon=을 반드시 지정해야
    한다 — 각 링크는 <a data-testid="stSidebarNavLink"> 안에 span 2개(아이콘, 라벨)를
    순서대로 담는데, icon이 없는 페이지는 라벨 span이 첫 번째가 되어 대신 숨겨진다.
    페이지 링크가 아닌 사이드바의 나머지 내용(로그아웃 버튼 등)은 이 선택자들이
    안 건드리므로 그대로 보인다.
    """
    st.html(f"""
    <style>
    [data-testid="stSidebar"] {{
        min-width: 68px !important;
        max-width: 68px !important;
        width: 68px !important;
    }}
    [data-testid="stSidebarNavLink"] {{
        justify-content: center;
    }}
    [data-testid="stSidebarNavLink"] > span:last-child {{
        display: none;
    }}
    [data-testid="stSidebarUserContent"] {{
        padding-left: 0.35rem;
        padding-right: 0.35rem;
    }}
    </style>
    """)
