from typing import Any, Dict

import requests


class SarApiError(RuntimeError):
    pass


class SarApiTimeout(SarApiError):
    pass


class SarApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def health(self) -> Dict[str, Any]:
        return self._get_json("/health", timeout=3)

    def infer(self, tif_file: Any, rotate_k: int) -> Dict[str, Any]:
        return self._post_upload(
            "/sar/infer",
            tif_file=tif_file,
            rotate_k=rotate_k,
            timeout=600,
        )

    def _get_json(self, path: str, timeout: int) -> Dict[str, Any]:
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
        if response.status_code == 200:
            return response.json()
        raise SarApiError(f"서버 오류 {response.status_code}: {response.text}")
