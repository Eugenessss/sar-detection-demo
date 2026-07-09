# 청출어람 — EO/SAR 위성영상 기반 표적 후보 탐지 및 판독 지원 서비스

SAR 영상(YOLO11n 탐지 + ConvNeXt-Tiny 14종 분류)과 EO(전자광학) 영상(YOLO 표적 탐지)에서 표적 후보를 찾아 판독을 돕는 서비스입니다. **단일 Streamlit 앱**으로 구성되어 있으며, 화면과 추론 로직이 한 프로세스 안에서 함수 호출로 연결됩니다 (별도 백엔드 서버 없음).

## 프로젝트 구조

페이지(기능) 단위로 수직 분할되어 있습니다. "SAR에 관한 것은 `features/sar/` 안에 다 있다"가 원칙입니다.

```text
demo/
├─ app.py                       # Streamlit 진입점, 페이지 라우팅 (Home/SAR/EO/DB)
├─ home.py                      # 메인(홈) 소개 페이지
├─ placeholders.py              # 임시(빈) 페이지 렌더러
├─ features/                    # 페이지(기능) 단위 모듈
│  ├─ sar/
│  │  ├─ view.py                # SAR 추론 화면 (입력 → 실행 → 결과 표시 → DB 저장)
│  │  ├─ service.py             # 추론 유스케이스 (임시저장 → 로딩 → 회전 → 파이프라인 → 결과 조립)
│  │  ├─ repository.py          # satellite_intel 조회/저장 (이미지 정보, 탐지 집계)
│  │  ├─ loader.py              # @st.cache_resource 모델 1회 로드
│  │  ├─ pipeline.py            # 탐지+분류 파이프라인 (회전 → 탐지 → 분류 → 좌표 복원)
│  │  ├─ detect.py              # YOLO 기반 탐지
│  │  ├─ classify.py            # ConvNeXt 기반 분류
│  │  ├─ rotation.py            # 회전/좌표 변환
│  │  ├─ image.py               # SAR 이미지 로딩/밝기 정규화 (추론용·표시용)
│  │  ├─ models.py              # 모델 보관소 (로드 상태와 getter)
│  │  └─ config.py              # 가중치 경로 및 하이퍼파라미터
│  ├─ eo/
│  │  ├─ view.py                # EO 탐지 화면
│  │  ├─ service.py             # 추론 유스케이스
│  │  ├─ loader.py              # @st.cache_resource 모델 1회 로드
│  │  ├─ detect.py              # YOLO 기반 EO 표적 탐지
│  │  ├─ image.py               # EO 이미지 로딩 (정규화 없음, 원본 색 그대로)
│  │  ├─ models.py              # 모델 보관소
│  │  └─ config.py              # 가중치 경로 및 하이퍼파라미터
│  └─ db/
│     ├─ view.py                # DB 조회 화면 (데이터베이스/테이블 선택 → 조회)
│     └─ service.py             # 읽기 전용 조회 (목록·미리보기, SQL 주입 방지)
├─ shared/                      # 모든 feature가 함께 쓰는 공용/인프라 (features를 참조하지 않음)
│  ├─ viz.py                    # 박스+라벨 그리기 (SAR·EO 공용)
│  ├─ database.py               # RDS MySQL 연결 (.env에서 접속 정보 로드)
│  └─ temp_files.py             # 업로드 바이트 임시 저장/정리
├─ checkpoints/                 # 모델 가중치 (git 미포함 — 직접 배치)
├─ results/                     # 클래스 메타데이터
├─ tests/
│  └─ unit/sar/test_rotation.py
├─ .env.example                 # DB 접속 정보 예시 (복사해 .env로 사용)
├─ requirements.txt
└─ README.md
```

의존 방향은 항상 아래로만 흐릅니다: `app.py → features/* → shared/`. feature끼리는 서로 import하지 않고, `shared/`는 feature를 모릅니다.

## 동작 흐름 (요청 → 응답)

사용자가 이미지를 올리고 "실행"을 누르면, 아래 순서로 데이터가 흐릅니다. 처음 코드를 보는 분은 이 순서대로 파일을 따라 읽으면 전체 그림이 잡힙니다. (SAR 기준, EO도 동일한 패턴)

```text
[사용자 브라우저]
      │  ① 이미지 업로드 + "실행" 클릭
      ▼
features/sar/view.py            ── 화면 입력을 받아 서비스 함수를 직접 호출
      │  ② service.run_inference(파일 바이트, 파일명, 회전값)   ← HTTP 없음, 그냥 함수 호출
      ▼
features/sar/service.py         ── 모델확인 → 임시저장 → 이미지 로딩 → 회전 결정
      │        └─ shared/temp_files.py, features/sar/image.py
      │  ③ run_full_inference(...)
      ▼
features/sar/pipeline.py        ── 회전 → 탐지 → 분류 → 좌표 되돌리기 순서로 조립
      │        ├─ rotation.py  (이미지 회전 / 박스 좌표 역변환)
      │        ├─ detect.py    (차량 위치 박스 찾기, 모델은 models.py에서 꺼냄)
      │        └─ classify.py  (각 박스가 어떤 차량인지 판별)
      │  ④ 탐지 결과 + 표시용 이미지 반환 (직렬화 없음, 메모리 그대로)
      ▼
features/sar/view.py            ── 원본 이미지 위에 박스를 그리고 표로 표시
               └─ shared/viz.py (박스 그리기)
```

- 모델은 첫 사용 시 `features/<도메인>/loader.py`의 `@st.cache_resource`가 **프로세스당 한 번만** 로드하고 이후 재사용합니다.
- 에러는 파이썬 예외(`ModelUnavailableError` 등)로 그대로 전달됩니다. HTTP 상태코드 변환이 없습니다.
- 각 파일 맨 위의 설명 주석(docstring)을 먼저 읽으면 그 파일이 이 흐름에서 어디에 해당하는지 알 수 있습니다.

## 모델 및 데이터 파일

기본 artifact root는 **프로젝트 루트**입니다. 다른 위치를 사용하려면 SAR은 `SAR_ARTIFACT_DIR`, EO는 `EO_ARTIFACT_DIR` 환경변수로 `checkpoints/`(및 SAR은 `results/`)를 포함하는 디렉터리를 지정하세요.

| 경로 | 설명 |
| --- | --- |
| `checkpoints/yolo_detector_yolo11n.pt` | (SAR) YOLO11n 탐지기 가중치 |
| `checkpoints/convnext_soc14_final.pth` | (SAR) ConvNeXt-Tiny 분류기 가중치 |
| `results/convnext_soc14.json` | (SAR) 클래스 메타데이터 |
| `checkpoints/best.pt` | (EO) YOLO 표적 탐지기 가중치 (클래스 정보는 가중치에 내장) |

가중치 파일(`*.pt`, `*.pth`)은 git에 포함되지 않으므로 별도로 받아 `checkpoints/`에 넣어야 합니다.

## 실행 방법

```powershell
conda create -n sar-demo python=3.10 -y
conda activate sar-demo
pip install -r requirements.txt
```

실행은 명령 하나입니다:

```powershell
streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

### 자주 겪는 문제

| 증상 | 원인 / 해결 |
| --- | --- |
| SAR/EO 페이지에 "모델 미로드" 배지 | `checkpoints/`의 가중치 파일(`*.pt`, `*.pth`)이 없는 것 (git에 포함되지 않음) → 파일을 받아 넣고 새로고침 |
| DB 페이지 "DB 연결 실패" | 프로젝트 루트의 `.env` 접속 정보(`DB_HOST` 등) 확인 (아래 "데이터베이스 연동" 참고) |
| 포트가 이미 사용 중 | `streamlit run app.py --server.port 8502`처럼 변경 |
| 추론이 오래 걸림 | CPU 환경에서는 정상입니다. 특히 EO는 큰 입력 크기(2400px)로 추론하므로 수십 초 걸릴 수 있습니다 |

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

특정 데이터베이스를 고정하지 않고 서버에 접속하며, 조회 화면에서 데이터베이스를 골라서 봅니다.

앱을 켜지 않고 접속만 빠르게 확인하려면:

```powershell
python -m shared.database
```

관련 코드는 `shared/database.py`(연결 설정 — 인프라)와 `features/db/`(조회 화면·로직)에 있습니다. 안전을 위해 임의 SQL 실행은 제공하지 않고, 읽기 전용 조회(데이터베이스/테이블 목록, 상위 행 미리보기)만 지원합니다.

### SAR 페이지 DB 연동 (satellite_intel)

SAR 페이지는 `satellite_intel` 스키마와 연동됩니다 (`features/sar/repository.py`).

- **업로드 파일명이 image_id 역할**을 합니다 (예: `8192.tif` → `image_analysis`의 image_id 8192).
- 추론이 끝나면 `image_analysis`에서 자산·지역·센서·촬영시각을 조회해 "투입 이미지 정보"로 보여줍니다.
- **"DB 저장" 버튼**을 누르면 최종 검출목록(편집 반영)을 클래스별로 집계해 `detection_result`에 저장합니다.
  - `created_at` = 버튼을 누른 시스템 시간, `avg_confidence` = 미사용 방침이라 0
  - 같은 image_id로 다시 저장하면 기존 행을 덮어씁니다 (중복 누적 없음)
- 모델 라벨과 `equipment.class_name`은 직접 매치됩니다 (표기 통일 완료: BMP2, BRDM_2, BTR_60, BTR70, T62, T72, ZSU_23_4). equipment에 없는 라벨(직접 추가한 박스 등)은 경고 후 저장에서 제외됩니다.
- 파일명이 image_id 형식이 아니거나 DB에 없는 이미지면, 탐지는 정상 동작하고 DB 표시·저장만 생략됩니다.

## 테스트

```powershell
python -m unittest discover tests
```

현재는 회전 좌표 변환 단위 테스트가 포함되어 있습니다.

## 새 페이지 추가 방법

1. `features/<도메인>/` 폴더를 만들고 `view.py`(화면)를 작성합니다. 추론·조회 로직이 있다면 `service.py`로 분리합니다.
2. `app.py`에서 `render_<도메인>_page`를 import하고 `pages` 목록에 `st.Page(...)`로 등록합니다.
3. 여러 페이지가 함께 쓰는 기능이 생기면 그때 `shared/`로 옮깁니다 (처음부터 shared에 두지 않기).
