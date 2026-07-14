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


st.set_page_config(page_title="청출어람", layout="wide")

# 상단 메뉴에 노출할 페이지 목록. Home이 기본(접속 시 처음 보이는) 페이지다.
pages = [
    st.Page(render_home_page, title="Home", url_path="home", default=True),
    st.Page(render_sar_page, title="SAR", url_path="sar"),
    st.Page(render_eo_page, title="EO", url_path="eo"),
    st.Page(render_eosar_page, title="EO/SAR", url_path="eosar"),
    st.Page(render_db_page, title="DB", url_path="db"),
    st.Page(render_alerts_page, title="Alerts", url_path="alerts"),
    st.Page(render_statistics_page, title="Statistics", url_path="statistics"),
    st.Page(render_hq_desk_page, title="HQ Desk", url_path="hq-desk"),
    st.Page(render_reports_page, title="Reports", url_path="reports"),
    st.Page(render_blank_1_page, title="Blank 1", url_path="blank-1"),
]

# 다른 페이지(예: HQ Desk의 경보 목록)에서 st.switch_page()로 이 페이지들로 이동할 수
# 있도록 url_path -> StreamlitPage 매핑을 세션에 저장해둔다. callable 기반 페이지는
# 파일 경로가 아니라 st.navigation에 등록된 이 StreamlitPage 객체 자체가 있어야
# st.switch_page로 이동할 수 있다.
st.session_state["_pages_by_url"] = {p.url_path: p for p in pages}

current_page = st.navigation(pages, position="top")
current_page.run()
