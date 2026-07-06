"""
[EO 도메인 - 설정]
EO(전자광학, 즉 일반 위성/항공 사진) 탐지에 쓰는 가중치 경로와 추론 설정값.
가중치를 교체하거나 탐지 민감도를 조절할 때 여기 값만 바꾸면 된다.
"""
import os
from pathlib import Path

# 이 파일 기준으로 backend/ 폴더를 가리킨다. (환경변수 EO_ARTIFACT_DIR로 변경 가능)
BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = Path(os.getenv("EO_ARTIFACT_DIR", str(BASE_DIR)))

# --- weight path (가중치 파일 경로) ---
DET_WEIGHT = ARTIFACT_DIR / "checkpoints" / "best.pt"   # EO 탐지기(YOLO) 가중치

# --- detection hyperparameters (탐지 관련 숫자값) ---
DET_CONF  = 0.25   # 이 확신도(25%) 미만의 탐지는 버린다
DET_IMGSZ = 640    # 학습할 때와 동일한 입력 크기 (반드시 맞춰야 함)
