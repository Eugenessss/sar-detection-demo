"""
[SAR 도메인 - 모델 로더]
SAR 탐지기·분류기를 Streamlit 프로세스당 '딱 한 번'만 메모리에 올리는 파일.
예전 백엔드의 lifespan(앱 시작 시 프리로드) 역할을 @st.cache_resource가 대신한다.
view.py가 화면을 그리기 전에 이 함수를 불러 모델을 준비/상태확인한다.
"""
import streamlit as st

from features.sar import models
from features.sar.config import CLS_JSON, CLS_WEIGHT, DET_WEIGHT


@st.cache_resource(show_spinner="SAR 모델 로딩 중...")
def load_sar_models():
    """SAR 탐지기·분류기를 한 번만 로드하고 (성공여부, 오류) 를 돌려준다."""
    return models.load_models(DET_WEIGHT, CLS_WEIGHT, CLS_JSON)
