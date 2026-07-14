"""
[공용 - 로그인 인증]
app_user 테이블(login_id/password_hash/role/is_active)로 로그인을 검증한다.
분석관(ANALYST)/지휘관(COMMANDER) 역할에 따라 app.py가 다른 메뉴를 보여준다.
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


@dataclass
class AuthUser:
    """로그인한 사용자. 세션에 보관해두고 역할별 메뉴 분기에 쓴다."""
    user_id: int
    login_id: str
    user_name: str
    role: str  # app_user.role 원본값: 'ANALYST' | 'COMMANDER'


def authenticate(login_id: str, password: str) -> Optional[AuthUser]:
    """아이디·비밀번호가 맞고 계정이 활성(is_active=1)이면 사용자 정보를 돌려준다.

    password_hash 컬럼은 이름과 달리 현재 시드 데이터가 평문("1234")으로 들어있어
    평문으로 비교한다. 나중에 실제 해시로 채워지면 이 비교 부분만 해시 검증으로
    바꾸면 된다.
    """
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT user_id, login_id, user_name, role "
                f"FROM `{_DB}`.`app_user` "
                "WHERE login_id = :login_id AND password_hash = :password AND is_active = 1"
            ),
            {"login_id": login_id, "password": password},
        ).fetchone()
    if row is None:
        return None
    m = dict(row._mapping)
    return AuthUser(
        user_id=int(m["user_id"]),
        login_id=m["login_id"],
        user_name=m["user_name"],
        role=m["role"],
    )
