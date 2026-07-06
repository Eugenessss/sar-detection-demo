"""
[프론트엔드 - 백엔드 호출 클라이언트]
프론트엔드가 백엔드 FastAPI 서버와 대화하는 유일한 통로.
화면 코드(sar_page.py)는 여기 함수만 부르면 되고, HTTP 요청의 세부(주소·타임아웃·에러 처리)는
이 파일이 감춰준다. 프론트는 백엔드 파이썬 코드를 직접 import하지 않고 오직 이 HTTP 통로만 쓴다.
"""
from typing import Any, Dict

import requests


class SarApiError(RuntimeError):
    """백엔드 호출이 실패했을 때 화면에 보여줄 수 있도록 감싸는 예외."""
    pass


class SarApiTimeout(SarApiError):
    """요청이 정해진 시간 안에 끝나지 않았을 때의 예외."""
    pass


class SarApiClient:
    """백엔드 주소를 기억해두고, /health·/sar/infer 호출을 대신 해주는 클라이언트."""

    def __init__(self, base_url: str):
        """백엔드 기본 주소를 저장한다 (끝의 슬래시는 정리)."""
        self.base_url = base_url.rstrip("/")

    def health(self) -> Dict[str, Any]:
        """GET /health 를 호출해 서버·모델 상태를 받아온다."""
        return self._get_json("/health", timeout=3)

    def infer(self, tif_file: Any, rotate_k: int) -> Dict[str, Any]:
        """이미지와 회전값을 POST /sar/infer 로 보내 추론 결과를 받아온다."""
        return self._post_upload(
            "/sar/infer",
            tif_file=tif_file,
            rotate_k=rotate_k,
            timeout=600,
        )

    def _get_json(self, path: str, timeout: int) -> Dict[str, Any]:
        """GET 요청을 보내고 결과를 JSON으로 돌려준다 (실패는 우리 예외로 변환)."""
        try:
            response = requests.get(f"{self.base_url}{path}", timeout=timeout)
            return self._decode_response(response)
        except requests.exceptions.Timeout as exc:
            raise SarApiTimeout("요청 시간이 초과되었습니다.") from exc
        except requests.RequestException as exc:
            raise SarApiError(f"백엔드 연결 실패: {exc}") from exc

    def _post_upload(
        self,
        path: str,
        tif_file: Any,
        rotate_k: int,
        timeout: int,
    ) -> Dict[str, Any]:
        """이미지 파일을 multipart 형식으로 POST 하고 결과 JSON을 돌려준다."""
        files = {
            "tif": (
                tif_file.name,
                tif_file.getvalue(),
                tif_file.type or "application/octet-stream",
            )
        }

        try:
            response = requests.post(
                f"{self.base_url}{path}",
                data={"rotate_k": rotate_k},
                files=files,
                timeout=timeout,
            )
            return self._decode_response(response)
        except requests.exceptions.Timeout as exc:
            raise SarApiTimeout("요청 시간이 초과되었습니다.") from exc
        except requests.RequestException as exc:
            raise SarApiError(f"요청 실패: {exc}") from exc

    @staticmethod
    def _decode_response(response: requests.Response) -> Dict[str, Any]:
        """응답이 정상(200)이면 JSON을 돌려주고, 아니면 오류 내용을 예외로 던진다."""
        if response.status_code == 200:
            return response.json()
        raise SarApiError(f"서버 오류 {response.status_code}: {response.text}")
