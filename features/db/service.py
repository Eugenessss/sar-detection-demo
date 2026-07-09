"""
[DB 도메인 - 서비스]
RDS MySQL 서버의 데이터베이스·테이블을 읽기 전용으로 조회하는 순수 파이썬 함수.
화면(view.py)이 직접 호출한다.
안전을 위해 임의 SQL은 실행하지 않고, 존재하는 이름과 일치할 때만 조회한다(주입 방지).
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from shared.database import get_engine, ping

# MySQL 기본 시스템 데이터베이스 (조회 목록에서 숨긴다).
SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys"}


def check_connection() -> Tuple[bool, Optional[str]]:
    """DB에 접속되는지 확인해 (성공여부, 오류) 를 돌려준다."""
    return ping()


def list_databases() -> List[str]:
    """서버에 있는 (시스템 제외) 데이터베이스 이름 목록을 돌려준다."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name")
        )
        return [row[0] for row in rows if row[0] not in SYSTEM_SCHEMAS]


def list_tables(database: str) -> List[str]:
    """지정한 데이터베이스에 있는 테이블 이름 목록을 돌려준다."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :db ORDER BY table_name"
            ),
            {"db": database},
        )
        return [row[0] for row in rows]


def preview_table(database: str, table_name: str, limit: int = 50) -> Dict[str, Any]:
    """지정한 테이블 상위 몇 개 행(기본 50개)을 미리 본다."""
    # 데이터베이스·테이블 모두 실제 존재하는 이름과 정확히 일치할 때만 조회한다 (SQL 주입 방지).
    if database not in list_databases():
        raise ValueError(f"데이터베이스를 찾을 수 없습니다: {database}")
    if table_name not in list_tables(database):
        raise ValueError(f"테이블을 찾을 수 없습니다: {table_name}")

    safe_limit = max(1, min(int(limit), 500))
    with get_engine().connect() as conn:
        result = conn.execute(
            text(f"SELECT * FROM `{database}`.`{table_name}` LIMIT :limit"),
            {"limit": safe_limit},
        )
        rows = [dict(row._mapping) for row in result]

    return {
        "database": database,
        "table": table_name,
        "row_count": len(rows),
        "rows": rows,
    }
