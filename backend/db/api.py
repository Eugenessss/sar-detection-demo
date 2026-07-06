"""
[DB 도메인 - 조회 API]
DB 서버에 연결이 잘 되는지 확인하고, 데이터베이스·테이블 목록과 내용을 조회하는 엔드포인트 모음.
특정 DB에 고정되지 않고 서버의 모든 (사용자) 데이터베이스를 골라 조회할 수 있다.
안전을 위해 임의의 SQL을 실행하지는 않고, 아래 읽기 전용 조회만 제공한다.
  - GET /db/health            : DB 접속 여부 확인
  - GET /db/databases         : 데이터베이스(스키마) 목록
  - GET /db/tables            : 지정한 데이터베이스의 테이블 목록
  - GET /db/tables/{이름}     : 특정 테이블의 상위 몇 개 행 미리보기
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from backend.db.connection import get_engine, ping

router = APIRouter(prefix="/db", tags=["db"])

# MySQL 기본 시스템 데이터베이스 (조회 목록에서 숨긴다).
SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys"}


@router.get("/health")
def db_health() -> Dict[str, Any]:
    """DB에 접속되는지 확인해 결과를 돌려준다."""
    ok, err = ping()
    return {"connected": ok, "error": err}


def _list_databases() -> List[str]:
    """서버에 있는 (시스템 제외) 데이터베이스 이름 목록을 돌려준다."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name")
        )
        return [row[0] for row in rows if row[0] not in SYSTEM_SCHEMAS]


def _list_table_names(database: str) -> List[str]:
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


@router.get("/databases")
def list_databases() -> Dict[str, Any]:
    """서버의 데이터베이스 목록을 돌려준다."""
    try:
        return {"databases": _list_databases()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB 조회 실패: {exc}")


@router.get("/tables")
def list_tables(database: str = Query(...)) -> Dict[str, Any]:
    """지정한 데이터베이스의 테이블 목록을 돌려준다."""
    try:
        valid_databases = _list_databases()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB 조회 실패: {exc}")

    # 실제로 존재하는 데이터베이스와 정확히 일치할 때만 조회한다 (SQL 주입 방지).
    if database not in valid_databases:
        raise HTTPException(status_code=404, detail=f"데이터베이스를 찾을 수 없습니다: {database}")

    return {"database": database, "tables": _list_table_names(database)}


@router.get("/tables/{table_name}")
def preview_table(
    table_name: str,
    database: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    """지정한 데이터베이스의 특정 테이블 상위 몇 개 행(기본 50개)을 미리 본다."""
    try:
        valid_databases = _list_databases()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB 조회 실패: {exc}")

    # 데이터베이스·테이블 모두 실제 존재하는 이름과 일치할 때만 조회한다 (SQL 주입 방지).
    if database not in valid_databases:
        raise HTTPException(status_code=404, detail=f"데이터베이스를 찾을 수 없습니다: {database}")

    valid_tables = _list_table_names(database)
    if table_name not in valid_tables:
        raise HTTPException(status_code=404, detail=f"테이블을 찾을 수 없습니다: {table_name}")

    with get_engine().connect() as conn:
        result = conn.execute(
            text(f"SELECT * FROM `{database}`.`{table_name}` LIMIT :limit"),
            {"limit": limit},
        )
        columns = list(result.keys())
        rows = [dict(row._mapping) for row in result]

    return {
        "database": database,
        "table": table_name,
        "columns": columns,
        "row_count": len(rows),
        "rows": rows,
    }
