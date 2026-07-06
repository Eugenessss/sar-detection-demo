"""
[프론트엔드 - DB 백엔드 호출 클라이언트]
DB 페이지가 백엔드의 /db 엔드포인트와 대화하는 통로. 화면 코드(db_page.py)는 여기 함수만
부르면 되고, HTTP 요청의 세부(주소·타임아웃·에러 처리)는 이 파일이 감춰준다.
"""
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests


class DbApiError(RuntimeError):
    """백엔드 호출이 실패했을 때 화면에 보여줄 수 있도록 감싸는 예외."""
    pass


class DbApiClient:
    """백엔드 주소를 기억해두고 /db 조회 호출을 대신 해주는 클라이언트."""

    def __init__(self, base_url: str):
        """백엔드 기본 주소를 저장한다 (끝의 슬래시는 정리)."""
        self.base_url = base_url.rstrip("/")

    def health(self) -> Dict[str, Any]:
        """GET /db/health 로 DB 접속 여부를 확인한다."""
        return self._get("/db/health", timeout=5)

    def list_databases(self) -> Dict[str, Any]:
        """GET /db/databases 로 서버의 데이터베이스 목록을 받아온다."""
        return self._get("/db/databases", timeout=10)

    def list_tables(self, database: str) -> Dict[str, Any]:
        """GET /db/tables 로 지정한 데이터베이스의 테이블 목록을 받아온다."""
        return self._get("/db/tables", timeout=10, params={"database": database})

    def preview_table(self, database: str, table_name: str, limit: int = 50) -> Dict[str, Any]:
        """GET /db/tables/{table_name} 로 특정 테이블의 상위 행을 받아온다."""
        return self._get(
            f"/db/tables/{quote(table_name)}",
            timeout=30,
            params={"database": database, "limit": limit},
        )

    def _get(self, path: str, timeout: int, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """공통 GET 요청 처리 (실패는 우리 예외로 변환)."""
        try:
            response = requests.get(f"{self.base_url}{path}", params=params, timeout=timeout)
            return self._decode_response(response)
        except requests.exceptions.Timeout as exc:
            raise DbApiError("요청 시간이 초과되었습니다.") from exc
        except requests.RequestException as exc:
            raise DbApiError(f"백엔드 연결 실패: {exc}") from exc

    @staticmethod
    def _decode_response(response: requests.Response) -> Dict[str, Any]:
        """응답이 정상(200)이면 JSON을 돌려주고, 아니면 오류 내용을 예외로 던진다."""
        if response.status_code == 200:
            return response.json()
        raise DbApiError(f"서버 오류 {response.status_code}: {response.text}")
