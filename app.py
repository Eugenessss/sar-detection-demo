"""Streamlit 통합 앱의 진입점과 역할 기반 페이지 라우팅."""
import sys
from pathlib import Path

import streamlit as st

# 이 파일(app.py)이 있는 프로젝트 최상위 폴더를 import 경로에 넣어
# features/·shared/ 패키지를 어디서 실행하든 불러올 수 있게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from features.alerts.view import render_alerts_page
from features.eosar.view import render_eosar_page
from features.HQ_DESK.view import render_hq_desk_page
from features.statistics.view import render_statistics_page
from features.EOSAR_compare.view import render_eosar_compare_page
from features.ANALYST_DESK.view import render_hq_desk_page as render_analyst_desk_page
from login import render_login_page
from shared.theme_sync import detect_ui_theme
from shared.ui.navigation import render_top_navigation
from shared.ui.styles import load_global_styles


st.set_page_config(
    page_title="청출어람 | 위성정보 판독 지원",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

auth_user = st.session_state.get("auth_user")

# 라이트/다크 전환은 커스텀 버튼이 아니라 Streamlit 네이티브 테마 전환(오른쪽 위
# ☰ 메뉴 > Settings > Choose app theme, .streamlit/config.toml의 [theme.light]/
# [theme.dark])을 그대로 쓴다. st.dataframe 같은 캔버스 기반 위젯은 CSS로 못
# 건드리는데, 저 메뉴로 실제 테마를 바꿔야만 그런 위젯도 같이 바뀐다. 페이지/내비
# 구성보다 먼저 읽어야 render_top_navigation()의 헤더 색도 맞출 수 있다.
#
# st.context.theme.type은 메뉴에서 테마를 바꿔도(심지어 다른 위젯을 눌러도) 안
# 갱신되고 로그아웃 후 재접속해야만 반영되는 문제가 있어서 안 쓴다. 대신
# detect_ui_theme()가 우리 CSS가 안 건드리는 네이티브 ☰ 메뉴 요소의 실제 글자색을
# 봐서 지금 테마를 직접 판정하고, 바뀐 걸 감지하면 그 자리에서 rerun까지 강제한다.
ui_theme = detect_ui_theme()
st.session_state["ui_theme"] = ui_theme

# 로그인 전에는 기본 내비게이션을 숨긴 채 로그인 페이지만 등록한다. 로그인 후에는
# 네이티브 상단 내비게이션(st.navigation(position="top"))이 역할별 페이지와 숨김
# 상세 페이지를 함께 라우터에 등록한다. 로그아웃하면 다시 로그인 페이지만 등록되므로
# 이전 역할의 메뉴와 URL 접근도 제거된다.
if auth_user is None:
    pages = [st.Page(render_login_page, title="로그인", url_path="login")]
    st.session_state.pop("_pages_by_url", None)
    current_page = st.navigation(pages, position="hidden")
else:
    # 역할별로 접근 가능한 메뉴를 나눈다: 분석관(ANALYST)은 분석 화면들,
    # 지휘관(COMMANDER)은 Commander Desk만 본다. 각 목록의 첫 항목이 기본 화면.
    if auth_user.role == "COMMANDER":
        visible_pages = [
            st.Page(
                render_hq_desk_page,
                title="지휘관 현황",
                icon=":material/shield_person:",
                url_path="hq-desk",
            ),
        ]
    else:
        visible_pages = [
            st.Page(
                render_analyst_desk_page,
                title="분석 현황",
                icon=":material/space_dashboard:",
                url_path="analyst-desk",
            ),
            st.Page(
                render_eosar_page,
                title="EO/SAR 판독",
                icon=":material/satellite_alt:",
                url_path="eosar",
            ),
            st.Page(
                render_eosar_compare_page,
                title="영상 비교",
                icon=":material/compare:",
                url_path="eosar-compare",
            ),
        ]

    # 다른 화면에서 st.switch_page()로 접근할 수 있지만 상단 메뉴에는 안 보이는 하위 페이지.
    hidden_pages = [
        st.Page(
            render_alerts_page,
            title="경보 상세",
            url_path="alerts",
            visibility="hidden",
        ),
        st.Page(
            render_statistics_page,
            title="상세 통계",
            url_path="statistics",
            visibility="hidden",
        ),
    ]

    def _logout() -> None:
        st.session_state.pop("auth_user", None)
        st.session_state.pop("_pages_by_url", None)
        st.rerun()

    role_label = "지휘관" if auth_user.role == "COMMANDER" else "영상판독관"
    logout_page = st.Page(
        _logout,
        title=f"로그아웃 ({auth_user.user_name}·{role_label})",
        icon=":material/logout:",
        url_path="logout",
    )

    # 다른 페이지(예: HQ Desk의 경보 목록)에서 st.switch_page()로 이 페이지들로 이동할 수
    # 있도록 url_path -> StreamlitPage 매핑을 세션에 저장해둔다. callable 기반 페이지는
    # 파일 경로가 아니라 st.navigation에 등록된 이 StreamlitPage 객체 자체가 있어야
    # st.switch_page로 이동할 수 있다.
    pages = [*visible_pages, logout_page, *hidden_pages]
    st.session_state["_pages_by_url"] = {p.url_path: p for p in pages}
    current_page = render_top_navigation(pages, ui_theme)

load_global_styles(ui_theme)
current_page.run()
