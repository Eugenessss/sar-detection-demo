"""
[프론트엔드 - EO 백엔드 호출 클라이언트]
EO 페이지가 백엔드와 대화하는 통로. 화면 코드(eo_page.py)는 여기 함수만 부르면 되고,
HTTP 요청의 세부(주소·타임아웃·에러 처리)는 이 파일이 감춰준다.
구조는 sar_api.py와 같으며, EO 전용 엔드포인트(/eo/infer)를 호출한다.
"""
from typing import Any, Dict

import requests


class EoApiError(RuntimeError):
    """백엔드 호출이 실패했을 때 화면에 보여줄 수 있도록 감싸는 예외."""
    pass


class EoApiClient:
    """백엔드 주소를 기억해두고 /health·/eo/infer 호출을 대신 해주는 클라이언트."""

    def __init__(self, base_url: str):
        """백엔드 기본 주소를 저장한다 (끝의 슬래시는 정리)."""
        self.base_url = base_url.rstrip("/")

    def health(self) -> Dict[str, Any]:
        """GET /health 를 호출해 서버·모델 상태를 받아온다."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=3)
            return self._decode_response(response)
        except requests.exceptions.Timeout as exc:
            raise EoApiError("요청 시간이 초과되었습니다.") from exc
        except requests.RequestException as exc:
            raise EoApiError(f"백엔드 연결 실패: {exc}") from exc

    def infer(self, image_file: Any) -> Dict[str, Any]:
        """이미지를 POST /eo/infer 로 보내 탐지 결과를 받아온다."""
        files = {
            "image": (
                image_file.name,
                image_file.getvalue(),
                image_file.type or "application/octet-stream",
            )
        }
        try:
            response = requests.post(
                f"{self.base_url}/eo/infer",
                files=files,
                timeout=600,
            )
            return self._decode_response(response)
        except requests.exceptions.Timeout as exc:
            raise EoApiError("요청 시간이 초과되었습니다.") from exc
        except requests.RequestException as exc:
            raise EoApiError(f"요청 실패: {exc}") from exc

    @staticmethod
    def _decode_response(response: requests.Response) -> Dict[str, Any]:
        """응답이 정상(200)이면 JSON을 돌려주고, 아니면 오류 내용을 예외로 던진다."""
        if response.status_code == 200:
            return response.json()
        raise EoApiError(f"서버 오류 {response.status_code}: {response.text}")
