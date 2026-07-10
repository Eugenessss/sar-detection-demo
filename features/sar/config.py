"""
[SAR 도메인 - 설정]
모델 가중치 파일 위치와 탐지/분류에 쓰이는 숫자값(하이퍼파라미터)을 한곳에 모아둔 파일.
가중치를 교체하거나 탐지 민감도를 조절할 때 여기 값만 바꾸면 나머지 코드는 건드릴 필요가 없다.
"""
import os
from pathlib import Path

# 이 파일(features/sar/config.py) 기준으로 프로젝트 최상위 폴더를 가리킨다.
BASE_DIR = Path(__file__).resolve().parents[2]
# 모델/데이터(checkpoints/, results/)가 놓인 최상위 폴더. 환경변수 SAR_ARTIFACT_DIR로 다른 위치를 지정할 수 있다.
ARTIFACT_DIR = Path(os.getenv("SAR_ARTIFACT_DIR", str(BASE_DIR)))

# --- weight paths (가중치 파일 경로) ---
DET_WEIGHT = ARTIFACT_DIR / "checkpoints" / "yolo_detector_yolo11n.pt"   # 탐지기(YOLO) 가중치
CLS_WEIGHT = ARTIFACT_DIR / "checkpoints" / "convnext_soc14_final.pth"   # 분류기(ConvNeXt) 가중치
CLS_JSON   = ARTIFACT_DIR / "results"     / "convnext_soc14.json"        # 클래스 이름 메타데이터

# --- detection hyperparameters (탐지 관련 숫자값) ---
DET_CONF        = 0.5    # 이 확신도 미만의 탐지는 버린다
DET_TILE_SIZE   = 400    # 큰 이미지를 잘라서 처리할 때 한 조각(타일)의 크기
DET_OVERLAP     = 0.25   # 타일끼리 겹치는 비율 (경계에 걸친 물체를 놓치지 않기 위함)
DET_BOX_MAX_PX  = 100    # 이보다 큰 박스는 버린다 (건물 등 차량이 아닌 것 제거)

# --- classification (분류 관련 숫자값) ---
CLS_WIN_SIZE    = 128    # 분류할 때 박스 중심을 기준으로 잘라내는 정사각형 창 크기
