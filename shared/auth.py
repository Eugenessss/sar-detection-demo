"""
[공용 - 로그인 인증]
app_user 테이블(login_id/password_hash/role/is_active)로 로그인을 검증한다.
분석관(ANALYST)/지휘관(COMMANDER) 역할에 따라 app.py가 다른 메뉴를 보여준다.

세션 토큰(create_session_token/resolve_session_token/revoke_session_token)은
st.session_state가 못 버티는 실제 브라우저 새로고침(shared/theme_sync.py가 테마
전환 시 자동으로 거는 window.location.reload() 포함)에도 로그인이 풀리지 않게
하려고 둔 것 — URL 쿼리스트링(?s=token)에 토큰만 남겨두면, 새로고침해도 URL은
그대로라 로그인 상태를 복원할 수 있다. 토큰 자체엔 아무 개인정보도 없고
(secrets.token_urlsafe라 추측 불가능), 서버 프로세스 메모리에만 사는 값이라
서버가 재시작되면 자동으로 무효화된다.
"""
import secrets
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


# 토큰 -> 로그인 사용자. 서버 프로세스 메모리에만 있고 DB에 안 남는다 (재시작하면
# 다 풀린다 -- 이 프로젝트 규모에서는 그걸로 충분하고, 여러 워커로 나눠 돌리는
# 배포는 애초에 고려 대상이 아니다).
_ACTIVE_TOKENS: dict[str, AuthUser] = {}


def create_session_token(user: AuthUser) -> str:
    """로그인 성공 시 발급한다. 호출한 쪽이 st.query_params["s"]에 넣어둬야 한다."""
    token = secrets.token_urlsafe(24)
    _ACTIVE_TOKENS[token] = user
    return token


def resolve_session_token(token: Optional[str]) -> Optional[AuthUser]:
    """URL의 ?s= 토큰으로 로그인 사용자를 복원한다 (없거나 무효하면 None)."""
    if not token:
        return None
    return _ACTIVE_TOKENS.get(token)


def revoke_session_token(token: Optional[str]) -> None:
    """로그아웃 시 토큰을 무효화한다."""
    if token:
        _ACTIVE_TOKENS.pop(token, None)
