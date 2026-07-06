"""
[프론트엔드 - DB 조회 화면]
DB 서버(RDS MySQL)의 데이터베이스·테이블을 선택해 내용을 조회하는 페이지.
흐름: 접속 확인 → DB 목록 → DB 선택 → 테이블 목록 → 테이블 선택 → '조회' → 결과를 표로 표시.
"""
import pandas as pd
import streamlit as st

from db_api import DbApiClient, DbApiError
from settings import DEFAULT_BACKEND_URL


def render_db_page() -> None:
    """DB 조회 페이지 전체를 그린다."""
    st.title("DB 조회")
    st.caption("RDS MySQL 데이터베이스·테이블 조회")

    client = DbApiClient(DEFAULT_BACKEND_URL)

    # 1) DB 접속 상태를 먼저 확인한다.
    try:
        health = client.health()
    except DbApiError as exc:
        st.error(str(exc))
        st.stop()

    if not health.get("connected"):
        st.error(f"DB 연결 실패: {health.get('error', '')}")
        st.info("backend 실행 위치의 .env 파일에서 접속 정보(DB_HOST 등)를 확인하세요.")
        st.stop()

    st.success("DB 연결됨")

    # 2) 데이터베이스 목록을 받아온다.
    try:
        databases = client.list_databases().get("databases", [])
    except DbApiError as exc:
        st.error(str(exc))
        st.stop()

    if not databases:
        st.warning("조회할 수 있는 데이터베이스가 없습니다.")
        st.stop()

    # 3) 데이터베이스 선택
    database = st.selectbox("데이터베이스 선택", databases)

    # 4) 선택한 데이터베이스의 테이블 목록을 받아온다.
    try:
        tables = client.list_tables(database).get("tables", [])
    except DbApiError as exc:
        st.error(str(exc))
        st.stop()

    if not tables:
        st.warning(f"'{database}'에 테이블이 없습니다.")
        st.stop()

    # 5) 테이블 선택 + 가져올 행 수 + 조회 버튼
    select_col, limit_col, action_col = st.columns([2, 1, 1], vertical_alignment="bottom")
    with select_col:
        table_name = st.selectbox("테이블 선택", tables)
    with limit_col:
        limit = st.number_input("가져올 행 수", min_value=1, max_value=500, value=50, step=10)
    with action_col:
        run_clicked = st.button("조회", type="primary", use_container_width=True)

    st.divider()

    if not run_clicked:
        return

    # 6) 선택한 테이블을 조회해 표로 보여준다.
    with st.spinner("조회 중..."):
        try:
            result = client.preview_table(database, table_name, limit=int(limit))
        except DbApiError as exc:
            st.error(str(exc))
            st.stop()

    rows = result.get("rows", [])
    st.subheader(f"{result['database']}.{result['table']} (상위 {result['row_count']}행)")
    if not rows:
        st.info("행이 없습니다.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
