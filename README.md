# DOM SAR 차량 탐지 데모

YOLO11n 탐지기와 ConvNeXt-Tiny 분류기를 사용해 SAR 이미지에서 차량을 탐지하고 14개 클래스로 분류하는 데모입니다. 백엔드는 FastAPI, 프론트엔드는 Streamlit으로 구성되어 있습니다.

## 프로젝트 구조

```text
demo/
├─ backend/
│  ├─ main.py                         # FastAPI 앱 조립, lifespan, router include
│  ├─ infrastructure/
│  │  └─ temp_files.py                # 업로드 파일 임시 저장/정리
│  ├─ services/
│  │  └─ health_service.py            # 앱 상태 응답 조립
│  ├─ routers/
│  │  ├─ health.py                    # GET /health
│  │  ├─ eo/
│  │  │  └─ __init__.py               # /eo 확장 지점
│  │  └─ sar/
│  │     ├─ __init__.py               # /sar prefix 라우터 조립
│  │     ├─ infer.py                  # POST /sar/infer
│  │     └─ schemas.py                # API 응답 스키마
│  └─ sar/
│     ├─ config.py                    # artifact 경로 및 하이퍼파라미터
│     ├─ models.py                    # 모델 로드 상태와 getter
│     ├─ detect.py                    # YOLO 기반 탐지
│     ├─ classify.py                  # ConvNeXt 기반 분류
│     ├─ rotation.py                  # 회전/좌표 변환
│     ├─ image.py                     # SAR 이미지 로딩/정규화
│     ├─ pipeline.py                  # 탐지+분류 파이프라인
│     └─ services/
│        ├─ inference_service.py      # 업로드 추론 use case
│        └─ model_registry.py         # 모델 로드/상태 확인
├─ frontend/
│  ├─ app.py                          # Streamlit 진입점, 페이지 라우팅
│  ├─ core/
│  │  └─ settings.py                  # 프론트 설정값
│  ├─ views/
│  │  ├─ inference.py                 # 추론 페이지
│  │  ├─ placeholders.py              # 임시 페이지 공통 렌더러
│  │  └─ blank_*.py                   # 기존 import 호환용 shim
│  ├─ components/
│  │  ├─ inference_controls.py        # 입력/설정 컨트롤
│  │  └─ result_view.py               # 추론 결과 표시
│  ├─ services/
│  │  └─ sar_api.py                   # FastAPI 호출 클라이언트
│  └─ utils/
│     └─ viz.py                       # 박스 시각화, 이미지 로딩
├─ tests/
│  └─ unit/sar/test_rotation.py
├─ requirements.txt
└─ README.md
```

## 모델 및 데이터 파일

기본 artifact root는 `backend/`입니다. 다른 위치를 사용하려면 `SAR_ARTIFACT_DIR` 환경변수로 `checkpoints/`, `results/`를 포함하는 디렉터리를 지정하세요.

| 경로 | 설명 |
| --- | --- |
| `backend/checkpoints/yolo_detector_yolo11n.pt` | YOLO11n 탐지기 가중치 |
| `backend/checkpoints/convnext_soc14_final.pth` | ConvNeXt-Tiny 분류기 가중치 |
| `backend/results/convnext_soc14.json` | 클래스 메타데이터 |

## 실행 방법

```powershell
conda create -n sar-demo python=3.10 -y
conda activate sar-demo
pip install -r requirements.txt
```

백엔드:

```powershell
uvicorn backend.main:app --port 8000
```

프론트엔드:

```powershell
streamlit run frontend/app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

프론트엔드의 기본 백엔드 주소는 `DOM_SAR_BACKEND_URL` 환경변수로 변경할 수 있습니다.

## API

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/health` | 모델 로드 상태 확인 |
| POST | `/sar/infer` | 이미지 업로드 기반 탐지 및 분류 |

`POST /sar/infer`는 multipart form을 사용합니다.

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `tif` | 예 | TIF, TIFF, PNG, JPG 이미지 파일 |
| `rotate_k` | 아니오 | 수동 회전값. 0, 1, 2, 3은 각각 0도, 90도, 180도, 270도 |

## 테스트

```powershell
python -m unittest discover tests
```

현재는 회전 좌표 변환 단위 테스트가 포함되어 있습니다. 추후 `inference_service`와 API integration test를 추가하면 라우터 변경이나 모델 교체 시 회귀를 더 빨리 잡을 수 있습니다.
