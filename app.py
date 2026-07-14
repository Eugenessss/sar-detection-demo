"""
[진입점]
Streamlit 통합 앱의 시작점. 'streamlit run app.py'로 실행하면 이 파일이 뜬다.
상단 메뉴에 페이지들(Home / SAR / EO / DB / Blank)을 등록하고, 선택된 페이지를 실행한다.
각 페이지의 실제 내용은 features/<도메인>/view.py에 있고, 여기서는 페이지 연결만 담당한다.
"""
import sys
from pathlib import Path

import streamlit as st

# 이 파일(app.py)이 있는 프로젝트 최상위 폴더를 import 경로에 넣어
# features/·shared/ 패키지를 어디서 실행하든 불러올 수 있게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from features.alerts.view import render_alerts_page
from features.db.view import render_db_page
from features.eo.view import render_eo_page
from features.eosar.view import render_eosar_page
from features.HQ_DESK.view import render_hq_desk_page
from features.reports.view import render_reports_page
from features.sar.view import render_sar_page
from features.statistics.view import render_statistics_page
from home import render_home_page
from placeholders import render_blank_1_page
from features.EOSAR_compare.view import render_eosar_compare_page
from features.ANALYST_DESK.view import render_hq_desk_page as render_analyst_desk_page
from login import render_login_page
from shared.ui_chrome import apply_global_polish, apply_icon_rail_nav


st.set_page_config(page_title="청출어람", layout="wide", initial_sidebar_state="expanded")
apply_global_polish()

auth_user = st.session_state.get("auth_user")

# st.navigation()은 매 실행마다 반드시 호출한다 (로그인 전이라고 건너뛰지 않는다).
# 예전엔 로그인 전엔 st.navigation() 호출 자체를 건너뛰고 st.stop()으로 멈췄는데,
# 그러면 로그아웃 직후 다시 그려질 때 브라우저에 남아있던 이전 상단 탭바가
# 지워지지 않는 문제가 있었다. 매번 호출하되 pages만 로그인 여부로 바꾸면,
# "탭이 없다"는 상태 자체도 매번 명시적으로 다시 알려주게 되어 깔끔히 사라진다.
if auth_user is None:
    pages = [st.Page(render_login_page, title="Login", url_path="login")]
    nav_position = "hidden"
else:
    # 역할별로 접근 가능한 메뉴를 나눈다: 분석관(ANALYST)은 분석 화면들,
    # 지휘관(COMMANDER)은 Commander Desk만 본다. 각 목록의 첫 항목이 기본 화면.
    # icon은 상단 탭바 대신 왼쪽 사이드바 아이콘 레일 내비게이션(position="sidebar")에
    # 쓰인다 — Streamlit 공식 st.Page(icon=...) 기능이라 커스텀 CSS 없이 동작한다.
    if auth_user.role == "COMMANDER":
        visible_pages = [
            st.Page(
                render_hq_desk_page, title="Commander Desk",
                icon=":material/shield:", url_path="hq-desk",
            ),
        ]
    else:
        visible_pages = [
            st.Page(
                render_analyst_desk_page, title="Analyst Desk",
                icon=":material/radar:", url_path="analyst-desk",
            ),
            st.Page(
                render_eosar_page, title="EO/SAR_detect",
                icon=":material/search:", url_path="eosar",
            ),
            st.Page(
                render_eosar_compare_page, title="EO/SAR_compare",
                icon=":material/compare:", url_path="EOSAR_compare",
            ),
        ]

    # 다른 화면에서 st.switch_page()로 접근할 수 있지만 메뉴에는 안 보이는 하위 페이지.
    hidden_pages = [
        st.Page(
            render_alerts_page,
            title="Alerts",
            icon=":material/notifications:",
            url_path="alerts",
            visibility="hidden",
        ),
        st.Page(
            render_statistics_page,
            title="Statistics",
            icon=":material/bar_chart:",
            url_path="statistics",
            visibility="hidden",
        ),
    ]

    pages = [*visible_pages, *hidden_pages]
    nav_position = "sidebar"

    # 다른 페이지(예: HQ Desk의 경보 목록)에서 st.switch_page()로 이 페이지들로 이동할 수
    # 있도록 url_path -> StreamlitPage 매핑을 세션에 저장해둔다. callable 기반 페이지는
    # 파일 경로가 아니라 st.navigation에 등록된 이 StreamlitPage 객체 자체가 있어야
    # st.switch_page로 이동할 수 있다.
    st.session_state["_pages_by_url"] = {p.url_path: p for p in pages}

# st.navigation()이 position="sidebar"일 때 이 호출 시점에 사이드바 맨 위에 아이콘
# 내비게이션을 그린다. 로그인한 사람 정보·로그아웃 버튼은 그 아래에 이어서 그려야
# "내비게이션 위 / 사용자 정보 아래" 순서가 되므로, 이 호출 다음에 둔다.
current_page = st.navigation(pages, position=nav_position)

if auth_user is not None:
    apply_icon_rail_nav()
    # 사이드바가 68px로 좁아서 "이름 (역할)" 캡션은 줄바꿈되며 어색해지므로 빼고,
    # 아이콘만 있는 로그아웃 버튼 하나로 대신한다 — 누구로 로그인했는지는 버튼에
    # 마우스를 올리면(help) 툴팁으로 보인다.
    with st.sidebar:
        st.divider()
        if st.button(
            "", icon=":material/logout:",
            help=f"{auth_user.user_name} ({auth_user.role}) — 로그아웃",
            use_container_width=True,
        ):
            del st.session_state["auth_user"]
            st.rerun()

current_page.run()
