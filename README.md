# 청출어람 — EO/SAR 위성영상 기반 표적 후보 탐지 및 판독 지원 서비스

SAR 영상(YOLO11n 탐지 + ConvNeXt-Tiny 14종 분류)과 EO(전자광학) 영상(YOLO 표적 탐지)에서 표적 후보를 찾아 판독을 돕는 서비스입니다. 백엔드는 FastAPI, 프론트엔드는 Streamlit으로 구성되어 있습니다.

## 프로젝트 구조

```text
demo/
├─ backend/
│  ├─ main.py                         # FastAPI 앱 조립, lifespan, router include
│  ├─ health.py                       # GET /health
│  ├─ temp_files.py                   # 업로드 파일 임시 저장/정리
│  ├─ db/
│  │  ├─ connection.py                # RDS MySQL 연결 설정 (.env에서 접속 정보 로드)
│  │  └─ api.py                       # /db testdb 조회 엔드포인트
│  ├─ eo/
│  │  ├─ api.py                       # POST /eo/infer 라우터 + 스키마 + 추론 use case + 모델 상태
│  │  ├─ config.py                    # EO 가중치 경로 및 하이퍼파라미터
│  │  ├─ models.py                    # EO 모델 로드 상태와 getter
│  │  └─ detect.py                    # YOLO 기반 EO 표적 탐지
│  └─ sar/
│     ├─ api.py                       # POST /sar/infer 라우터 + 스키마 + 추론 use case + 모델 상태
│     ├─ config.py                    # artifact 경로 및 하이퍼파라미터
│     ├─ models.py                    # 모델 로드 상태와 getter
│     ├─ detect.py                    # YOLO 기반 탐지
│     ├─ classify.py                  # ConvNeXt 기반 분류
│     ├─ rotation.py                  # 회전/좌표 변환
│     ├─ image.py                     # SAR 이미지 로딩/정규화
│     └─ pipeline.py                  # 탐지+분류 파이프라인
├─ frontend/
│  ├─ app.py                          # Streamlit 진입점, 페이지 라우팅 (Home/SAR/EO/DB)
│  ├─ settings.py                     # 프론트 설정값
│  ├─ home.py                         # 메인(홈) 소개 페이지
│  ├─ sar_page.py                     # SAR 추론 페이지 + 입력 컨트롤 + 결과 표시
│  ├─ eo_page.py                      # EO 추론 페이지 + 입력 컨트롤 + 결과 표시
│  ├─ db_page.py                      # DB 조회 페이지 (테이블 선택 → 조회)
│  ├─ placeholders.py                 # 임시 페이지 렌더러
│  ├─ sar_api.py                      # SAR 백엔드 호출 클라이언트
│  ├─ eo_api.py                       # EO 백엔드 호출 클라이언트
│  ├─ db_api.py                       # DB 백엔드 호출 클라이언트
│  └─ viz.py                          # 박스 시각화 + 이미지 로딩
├─ shared/
│  └─ image_norm.py                   # 이미지 정규화 (backend/sar/image.py, frontend/viz.py 공용)
├─ tests/
│  └─ unit/sar/test_rotation.py
├─ .env.example                       # DB 접속 정보 예시 (복사해 .env로 사용)
├─ requirements.txt
└─ README.md
```

도메인(`sar`, `eo`)별 폴더 구분은 유지하되, 그 안의 "라우터/서비스/스키마"처럼 세분화된 계층은 도메인당 파일 하나(`api.py`)로 병합했습니다. 새 도메인을 추가할 때는 `backend/<domain>/`, `frontend/<domain>_page.py`를 새로 만들면 됩니다.

## 동작 흐름 (요청 → 응답)

사용자가 이미지를 올리고 "실행"을 누르면, 아래 순서로 데이터가 흐릅니다. 처음 코드를 보는 분은 이 순서대로 파일을 따라 읽으면 전체 그림이 잡힙니다.

```text
[사용자 브라우저]
      │  ① 이미지 업로드 + "실행" 클릭
      ▼
frontend/sar_page.py            ── 화면 입력을 받아 백엔드 호출을 준비
      │  ② client.infer(파일, 회전값)
      ▼
frontend/sar_api.py             ── HTTP로 백엔드에 요청 (POST /sar/infer)
      │  ③ multipart 업로드
      ▼
backend/sar/api.py  (infer)     ── 요청을 받아 추론 use case 실행
      │  ④ ensure_models_loaded → 모델 준비 확인
      │  ⑤ prepare_uploaded_scene → 임시 저장 + 이미지 로딩
      │        └─ backend/temp_files.py, backend/sar/image.py
      │  ⑥ run_detection → 파이프라인 호출
      ▼
backend/sar/pipeline.py         ── 회전 → 탐지 → 분류 → 좌표 되돌리기 순서로 조립
      │        ├─ backend/sar/rotation.py  (이미지 회전 / 박스 좌표 역변환)
      │        ├─ backend/sar/detect.py    (차량 위치 박스 찾기, 모델은 models.py에서 꺼냄)
      │        └─ backend/sar/classify.py  (각 박스가 어떤 차량인지 판별)
      │  ⑦ 탐지 결과 목록 반환
      ▼
backend/sar/api.py              ── 결과 + 메타정보를 JSON(InferenceResponse)으로 조립해 응답
      │  ⑧ JSON 응답
      ▼
frontend/sar_page.py            ── 원본 이미지 위에 박스를 그리고 표로 표시
               └─ frontend/viz.py (박스 그리기)
```

- 모델은 서버가 켜질 때(`backend/main.py`의 lifespan) 한 번만 메모리에 올려두고(`backend/sar/models.py`), 요청마다 재사용합니다.
- 밝기 정규화(`shared/image_norm.py`)는 백엔드(추론용)와 프론트(표시용) 양쪽에서 같은 함수를 씁니다.
- 각 파일 맨 위의 설명 주석(docstring)을 먼저 읽으면 그 파일이 이 흐름에서 어디에 해당하는지 알 수 있습니다.

## 모델 및 데이터 파일

기본 artifact root는 `backend/`입니다. 다른 위치를 사용하려면 SAR은 `SAR_ARTIFACT_DIR`, EO는 `EO_ARTIFACT_DIR` 환경변수로 `checkpoints/`(및 SAR은 `results/`)를 포함하는 디렉터리를 지정하세요.

| 경로 | 설명 |
| --- | --- |
| `backend/checkpoints/yolo_detector_yolo11n.pt` | (SAR) YOLO11n 탐지기 가중치 |
| `backend/checkpoints/convnext_soc14_final.pth` | (SAR) ConvNeXt-Tiny 분류기 가중치 |
| `backend/results/convnext_soc14.json` | (SAR) 클래스 메타데이터 |
| `backend/checkpoints/best.pt` | (EO) YOLO 표적 탐지기 가중치 (클래스 정보는 가중치에 내장) |

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
| GET | `/health` | SAR·EO 모델 로드 상태 확인 |
| POST | `/sar/infer` | SAR 이미지 업로드 기반 탐지 및 분류 |
| POST | `/eo/infer` | EO 이미지 업로드 기반 표적 탐지 |
| GET | `/db/health` | DB(RDS MySQL) 접속 여부 확인 |
| GET | `/db/databases` | 데이터베이스(스키마) 목록 조회 |
| GET | `/db/tables?database=<db>` | 지정한 데이터베이스의 테이블 목록 조회 |
| GET | `/db/tables/{table_name}?database=<db>` | 특정 테이블의 상위 행 미리보기 (`limit` 1~500, 기본 50) |

`POST /sar/infer`는 multipart form을 사용합니다.

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `tif` | 예 | TIF, TIFF, PNG, JPG 이미지 파일 |
| `rotate_k` | 아니오 | 수동 회전값. 0, 1, 2, 3은 각각 0도, 90도, 180도, 270도 |

`POST /eo/infer`도 multipart form을 사용합니다.

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `image` | 예 | JPG, PNG, TIF 이미지 파일 |

## 데이터베이스 (RDS MySQL) 연동

접속 정보는 코드에 두지 않고 프로젝트 루트의 `.env` 파일에서 읽어옵니다. `.env.example`을 복사해 값을 채우세요. (`.env`는 git에 올라가지 않습니다.)

```powershell
copy .env.example .env   # 이후 .env 안의 DB_HOST/DB_USER/DB_PASSWORD 등을 실제 값으로 수정
```

| 환경변수 | 설명 | 기본값 |
| --- | --- | --- |
| `DB_HOST` | RDS 엔드포인트 주소 | (없음) |
| `DB_PORT` | 포트 | `3306` |
| `DB_USER` | 계정 | (없음) |
| `DB_PASSWORD` | 비밀번호 | (없음) |

특정 데이터베이스를 고정하지 않고 서버에 접속하며, 조회 화면(또는 API)에서 데이터베이스를 골라서 봅니다.

서버를 켜지 않고 접속만 빠르게 확인하려면:

```powershell
python -m backend.db.connection
```

관련 코드는 `backend/db/` 폴더에 있습니다 (`connection.py` 연결 설정, `api.py` 조회 엔드포인트). 안전을 위해 임의 SQL 실행은 제공하지 않고, 위 3개 읽기 전용 조회만 지원합니다.

프론트엔드에서는 상단 메뉴의 **DB** 페이지에서 접속 상태를 확인하고, 테이블을 선택해 내용을 조회할 수 있습니다 (`frontend/db_page.py`).

## 테스트

```powershell
python -m unittest discover tests
```

현재는 회전 좌표 변환 단위 테스트가 포함되어 있습니다. 추후 `backend/sar/api.py`의 추론 use case와 API integration test를 추가하면 라우터 변경이나 모델 교체 시 회귀를 더 빨리 잡을 수 있습니다.
