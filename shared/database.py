"""
[공용 - DB 연결]
AWS RDS의 MySQL 서버에 접속하기 위한 설정과 연결 객체(engine)를 만드는 파일.
접속 정보(주소·계정·비밀번호)는 보안을 위해 코드에 직접 쓰지 않고, 프로젝트 루트의
.env 파일이나 실행 환경의 환경변수에서 읽어온다. (예시는 .env.example 참고)

특정 페이지에 묶이지 않는 인프라 기능이라 shared/ 아래에 둔다.
engine은 앱이 실제로 DB를 처음 쓸 때 한 번만 만들어 재사용한다.
그래서 DB 정보가 없어도 이 파일을 import하는 것만으로는 에러가 나지 않는다.

사용 규칙 (각 feature의 DB 코드가 지켜야 할 것):
  - 읽기(SELECT)                : with get_engine().connect() as conn: ...
  - 쓰기(INSERT/UPDATE/DELETE)  : with get_engine().begin() as conn: ...
    begin()은 블록이 정상 종료되면 자동 커밋, 예외가 나면 자동 롤백한다.
    connect()로 쓰기를 실행하면 커밋 없이 조용히 롤백되므로 반드시 begin()을 쓴다.
  - 값은 항상 파라미터 바인딩(:name)으로 넘긴다. 테이블/DB 이름은 코드 상수만 f-string 허용.
"""
import os
import threading
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine

# 프로젝트 루트(.env가 놓인 곳)를 찾아 접속 정보를 환경변수로 불러온다.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

_engine: Optional[Engine] = None      # 한 번 만든 연결 객체를 담아 재사용
_engine_lock = threading.Lock()       # Streamlit은 세션마다 스레드라, 동시 생성을 막는다


def _build_url() -> URL:
    """환경변수에 담긴 접속 정보를 MySQL 접속 주소로 조립한다.

    URL.create()를 쓰면 비밀번호에 @ : / % 같은 특수문자가 있어도 안전하게 처리된다.
    특정 DB를 고정하지 않고 서버에 접속한다 (조회 시 데이터베이스를 골라서 지정).
    """
    return URL.create(
        "mysql+pymysql",
        username=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", ""),
        port=int(os.getenv("DB_PORT", "3306") or "3306"),
        query={"charset": "utf8mb4"},
    )


def get_engine() -> Engine:
    """DB 연결 객체(engine)를 한 번만 만들어 두고, 이후에는 그대로 재사용한다."""
    global _engine
    if _engine is None:
        with _engine_lock:          # 두 세션이 동시에 첫 접속해도 engine은 하나만 만든다
            if _engine is None:
                _engine = create_engine(
                    _build_url(),
                    pool_pre_ping=True,    # 오래돼 끊긴 연결을 자동 감지해 다시 연결
                    pool_recycle=3600,     # 1시간 넘은 유휴 연결은 재생성 (서버측 강제 종료 대비)
                    future=True,
                    # RDS 서버 기본 타임존(UTC) 때문에 NOW()/CURRENT_TIMESTAMP가 9시간
                    # 어긋나므로, 이 앱의 모든 연결을 한국시간(+09:00)으로 고정한다.
                    connect_args={"init_command": "SET time_zone = '+09:00'"},
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
    # 터미널에서 `python -m shared.database` 으로 접속 여부만 빠르게 확인할 수 있다.
    ok, err = ping()
    print("DB 연결 성공" if ok else f"DB 연결 실패: {err}")
