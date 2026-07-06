"""
[프론트엔드 - 설정값]
프론트엔드가 호출할 백엔드 서버 주소를 정해두는 파일.
환경변수 DOM_SAR_BACKEND_URL로 바꿀 수 있고, 없으면 로컬 기본값을 쓴다.
"""
import os


DEFAULT_BACKEND_URL = os.getenv("DOM_SAR_BACKEND_URL", "http://localhost:8000")
