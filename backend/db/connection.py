"""
[DB 도메인 - 연결 설정]
AWS RDS의 MySQL 서버에 접속하기 위한 설정과 연결 객체(engine)를 만드는 파일.
접속 정보(주소·계정·비밀번호)는 보안을 위해 코드에 직접 쓰지 않고, 프로젝트 루트의
.env 파일이나 실행 환경의 환경변수에서 읽어온다. (예시는 .env.example 참고)

engine은 앱이 실제로 DB를 처음 쓸 때 한 번만 만들어 재사용한다.
그래서 DB 정보가 없어도 이 파일을 import하는 것만으로는 에러가 나지 않는다.
"""
import os
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# 프로젝트 루트(.env가 놓인 곳)를 찾아 접속 정보를 환경변수로 불러온다.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

_engine: Optional[Engine] = None   # 한 번 만든 연결 객체를 담아 재사용


def _build_url() -> str:
    """환경변수에 담긴 접속 정보를 MySQL 접속 주소 문자열로 조립한다."""
    host = os.getenv("DB_HOST", "")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    # 특정 DB를 고정하지 않고 서버에 접속한다 (조회 시 데이터베이스를 골라서 지정).
    # 'mysql+pymysql://계정:비밀번호@주소:포트/' 형식 (pymysql 드라이버 사용)
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/?charset=utf8mb4"


def get_engine() -> Engine:
    """DB 연결 객체(engine)를 한 번만 만들어 두고, 이후에는 그대로 재사용한다."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _build_url(),
            pool_pre_ping=True,   # 오래돼 끊긴 연결을 자동 감지해 다시 연결
            future=True,
        )
    return _engine


def ping() -> Tuple[bool, Optional[str]]:
    """DB에 실제로 접속되는지 아주 간단한 쿼리(SELECT 1)로 확인한다."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc)


if __name__ == "__main__":
    # 터미널에서 `python -m backend.db.connection` 으로 접속 여부만 빠르게 확인할 수 있다.
    ok, err = ping()
    print("DB 연결 성공" if ok else f"DB 연결 실패: {err}")
