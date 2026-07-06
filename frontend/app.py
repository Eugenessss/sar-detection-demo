"""
[프론트엔드 진입점]
Streamlit 화면의 시작점. 'streamlit run frontend/app.py'로 실행하면 이 파일이 뜬다.
상단 메뉴에 페이지들(Inference + 빈 페이지 3개)을 등록하고, 선택된 페이지를 실행한다.
실제 추론 화면 내용은 sar_page.py에 있고, 여기서는 페이지 연결만 담당한다.
"""
import sys
from pathlib import Path

import streamlit as st

# frontend/ 폴더는 Streamlit이 자동으로 인식하지만 저장소 최상위 폴더는 아니다.
# shared/ 패키지를 import하려면 최상위 폴더를 경로에 추가해줘야 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db_page import render_db_page
from eo_page import render_eo_page
from home import render_home_page
from placeholders import render_blank_1_page
from sar_page import render_inference_page


st.set_page_config(page_title="청출어람", layout="wide")

# 상단 메뉴에 노출할 페이지 목록. Home이 기본(접속 시 처음 보이는) 페이지다.
pages = [
    st.Page(render_home_page, title="Home", url_path="home", default=True),
    st.Page(render_inference_page, title="SAR", url_path="sar"),
    st.Page(render_eo_page, title="EO", url_path="eo"),
    st.Page(render_db_page, title="DB", url_path="db"),
    st.Page(render_blank_1_page, title="Blank 1", url_path="blank-1"),
]

current_page = st.navigation(pages, position="top")
current_page.run()
