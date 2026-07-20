# 청출어람 (ARGOS) — EO/SAR 위성영상 기반 표적 탐지·판독 지원 시스템

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)
![Ultralytics YOLO](https://img.shields.io/badge/Ultralytics%20YOLO-111F68?style=for-the-badge&logo=ultralytics&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)

EO(전자광학)·SAR 위성영상에서 표적 후보를 탐지하고(EO: YOLO / SAR: YOLO 탐지 + ConvNeXt-Tiny 14종 분류), 변화 탐지 경보와 지휘 결심 기록까지 하나의 흐름으로 잇는 **단일 Streamlit 앱**입니다. 화면과 추론 로직이 한 프로세스 안에서 함수 호출로 연결됩니다 (별도 백엔드 서버 없음).

> **이 브랜치(`local-mysql`)는 AWS 없이 로컬 PC만으로 도는 시연용 버전입니다.**
> DB는 본인 PC의 MySQL(`local_data/satellite_intel_dump.sql`로 복원), 이미지는
> 저장소에 포함된 `original_image/`·`result_image/` 폴더를 그대로 사용합니다.
> 설정 절차는 아래 [로컬 시연 설정](#로컬-시연-설정-3단계)을 따라 하면 됩니다.

## 화면 구성 (로그인 · 역할 기반)

`app_user` 테이블 계정으로 로그인하면 역할에 맞는 메뉴만 상단 내비게이션에 표시됩니다.

| 역할 | 메뉴 | 내용 |
| --- | --- | --- |
| 분석관 (ANALYST) | 분석 현황 | 경보 상황 지도 + 최근 24시간 지역별 탐지 추이 |
| | EO/SAR 판독 | 원본 풀에서 선택 → 센서 자동 판별 → 탐지 → 검출 검토/편집 → DB 저장·보고서 |
| | 영상 비교 | 같은 지역·시각의 EO/SAR × 원본/분석 4패널 비교 + HTML 보고서 |
| | (숨김) 경보 상세 / 상세 통계 | 메뉴에는 없고 다른 화면에서 `st.switch_page`로 진입 |
| 지휘관 (COMMANDER) | 지휘관 현황 | 경보 지도·우선 경보 목록 → 경보 상세(위성영상·타격 옵션·타격/대기 결심 기록) |

## 프로젝트 구조

페이지(기능) 단위로 수직 분할되어 있습니다. "EO/SAR 판독에 관한 것은 `features/eosar/` 안에 다 있다"가 원칙입니다.

```text
demo/
├─ app.py                       # 진입점 — 로그인 여부·역할에 따라 페이지를 라우터에 등록
├─ login.py                     # 로그인 화면 (shared/auth.py로 app_user 인증 → 세션 저장)
├─ features/
│  ├─ ANALYST_DESK/             # 분석 현황 (경보 지도 + 24시간 지역별 탐지 추이)
│  ├─ eosar/                    # EO/SAR 통합 판독 (원본 풀 → 탐지 → 검토 → DB 저장·보고서)
│  ├─ EOSAR_compare/            # 영상 비교 (4패널 비교 보드 + 자가완결형 HTML 보고서)
│  ├─ alerts/                   # 경보 확인/상세 (변화 탐지 경보 조회·확인 처리·보고 초안)
│  ├─ statistics/               # 상세 통계 (기간·지역·위협등급·장비별 집계 + 통계 보고서)
│  ├─ HQ_DESK/                  # 지휘관 현황 + 경보 상세 (아군 자산·타격 옵션·결심 기록)
│  ├─ reports/                  # 분석 보고서 양식·조회 (eosar 페이지가 재사용)
│  ├─ eo/, sar/                 # 센서별 추론 파이프라인 (loader/detect/classify/rotation/…)
│  └─ db/, commander/           # 레거시 — 현재 메뉴에 등록되지 않음
├─ home.py, placeholders.py     # 레거시 — 구 라우팅용, 현재 미사용
├─ shared/                      # 모든 feature가 함께 쓰는 공용/인프라 (features를 참조하지 않음)
│  ├─ ui/                       # 상단 navbar, 페이지 헤더·메트릭 카드 등 공용 UI + 전역 CSS 로더
│  ├─ charts.py                 # Altair 차트 공통 팔레트·축 테마
│  ├─ eo_map.py                 # Earth Engine Sentinel-2 지도 공통 생성·캐시
│  ├─ auth.py                   # app_user 로그인 검증
│  ├─ database.py               # 로컬 MySQL 연결 (.env에서 접속 정보 로드)
│  ├─ s3_store.py               # 원본/결과 이미지 저장소 (로컬 폴더 — S3 버전과 같은 인터페이스)
│  ├─ image_store.py            # image_analysis·detection_result 공용 저장 로직
│  ├─ change_analysis.py        # DB 저장 직후 직전 촬영분과 비교해 변화 경보(alert) 생성
│  └─ alert_ui.py, viz.py, temp_files.py
├─ assets/                      # 전역 CSS(css/app.css)·ARGOS 로고 이미지
├─ .streamlit/config.toml       # 라이트 테마·차트 카테고리 팔레트
├─ checkpoints/                 # 모델 가중치 (git 미포함 — 직접 배치)
├─ results/                     # 클래스 메타데이터
├─ tests/
│  └─ unit/sar/test_rotation.py
├─ local_data/                  # satellite_intel DB 전체 덤프 (Workbench에서 실행해 복원)
├─ .env.example                 # 로컬 MySQL 접속 정보 예시 (복사해 .env로 사용)
├─ requirements.txt
└─ README.md
```

의존 방향은 항상 아래로만 흐릅니다: `app.py → features/* → shared/`. feature끼리는 서로 import하지 않는 것이 원칙입니다 (예외: `eosar`가 센서 파이프라인인 `eo`/`sar`와 보고서 양식인 `reports`를 호출).

## 동작 흐름 (EO/SAR 판독 기준)

```text
[분석관 브라우저]
      │  ① 원본 폴더(original_image/) 목록에서 파일 선택 → "분석 실행"
      ▼
features/eosar/view.py          ── 파일명에서 센서(EO/SAR)·자산·지역·촬영시각을 파싱
      │  ② EO → features/eo/service.run_inference
      │     SAR → features/sar/service.run_inference      ← HTTP 없음, 그냥 함수 호출
      ▼
features/<eo|sar>/…             ── 모델 로드(@st.cache_resource, 프로세스당 1회)
      │                            → 탐지(+SAR은 분류·회전 보정) → 결과 조립
      │  ③ 오른쪽 검토 레일에서 검출 목록 확인·수정/삭제/추가
      ▼
"DB 저장" 버튼                  ── 결과 이미지 저장(result_image/)
      │                            → image_analysis·detection_result 저장 (shared/image_store.py)
      │  ④ shared/change_analysis.py — 직전 촬영분과 비교해 변화 경보(alert) 생성
      ▼
분석 현황·지휘관 현황의 지도/그래프와 경보 화면에 반영
```

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

## 로컬 시연 설정 (3단계)

AWS 없이 본인 PC의 MySQL만 있으면 됩니다. (MySQL Workbench 기준)

**① DB 복원** — MySQL Workbench에서 로컬 서버에 접속한 뒤,
`File > Open SQL Script`로 `local_data/satellite_intel_dump.sql`을 열고 실행(⚡)합니다.
`satellite_intel` 데이터베이스(테이블 10개, 탐지 이력·경보·계정 포함)가 통째로 만들어집니다.

**② 접속 정보 작성** — `.env.example`을 복사해 `.env`를 만들고 본인 MySQL 계정을 채웁니다.

```powershell
copy .env.example .env   # DB_HOST=localhost, DB_USER/DB_PASSWORD를 본인 것으로
python -m shared.database   # (선택) 앱을 켜기 전에 DB 접속 확인 — "DB 연결 성공"이 나오면 OK
```

**③ 모델 가중치 배치** — 별도로 전달받은 가중치 파일을 `checkpoints/` 폴더에 넣습니다
(용량 문제로 git에 포함되지 않음 — 아래 "모델 및 데이터 파일" 참고).

로그인 계정은 복원된 `app_user` 테이블에 들어 있습니다 (분석관·지휘관 각 1개).
원본/결과 이미지는 저장소의 `original_image/`·`result_image/` 폴더에 이미 포함되어 있어 추가 설정이 없습니다.

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

브라우저에서 `http://localhost:8501`로 접속한 뒤, `app_user` 테이블의 분석관 또는 지휘관 계정으로 로그인합니다.

> 지도(분석 현황·지휘관 현황·경보 상세)는 Google Earth Engine의 Sentinel-2 타일을 사용합니다.
> 처음 실행하는 PC에서는 `earthengine authenticate`로 1회 인증이 필요합니다 (미인증 시 첫 지도 로드 때 인증 창이 뜹니다).

### 자주 겪는 문제

| 증상 | 원인 / 해결 |
| --- | --- |
| EO/SAR 판독에 "모델 미로드" 배지 | `checkpoints/`의 가중치 파일(`*.pt`, `*.pth`)이 없는 것 (git에 포함되지 않음) → 파일을 받아 넣고 새로고침 |
| 로그인 오류 / "DB 연결 실패" | MySQL 서버가 켜져 있는지, `.env` 접속 정보(`DB_HOST`·`DB_USER`·`DB_PASSWORD`)가 맞는지 확인. `python -m shared.database`로 빠르게 진단 |
| "Unknown database 'satellite_intel'" | ①번 DB 복원(덤프 실행)을 안 한 것 → `local_data/satellite_intel_dump.sql` 실행 |
| EO/SAR 판독의 원본 목록이 비어 있음 | 프로젝트의 `original_image/` 폴더가 비어 있는 것 (git clone이 정상이면 포함되어 있음) |
| 지도가 안 뜸 / Earth Engine 오류 | `earthengine authenticate`로 인증했는지 확인 |
| 포트가 이미 사용 중 | `streamlit run app.py --server.port 8502`처럼 변경 |
| 추론이 오래 걸림 | CPU 환경에서는 정상입니다. 특히 EO는 큰 입력 크기(2400px)로 추론하므로 수십 초 걸릴 수 있습니다 |

## 데이터베이스 (로컬 MySQL) · 이미지 저장소

접속 정보는 코드에 두지 않고 프로젝트 루트의 `.env` 파일에서 읽어옵니다 (위 "로컬 시연 설정" 참고).

| 환경변수 | 설명 | 기본값 |
| --- | --- | --- |
| `DB_HOST` | MySQL 서버 주소 (로컬이면 `localhost`) | (없음) |
| `DB_PORT` | 포트 | `3306` |
| `DB_USER` | 계정 (예: `root`) | (없음) |
| `DB_PASSWORD` | 비밀번호 | (없음) |

원본/결과 이미지는 프로젝트의 `original_image/`·`result_image/` 폴더가 저장소입니다
(`shared/s3_store.py` — S3를 쓰던 버전과 같은 인터페이스의 로컬 폴더 구현이라 이름만 s3_store입니다).
DB의 `image_analysis`에는 폴더 기준 상대경로만 기록됩니다.

### satellite_intel 스키마 연동

EO/SAR 판독 페이지가 `shared/image_store.py`의 공용 저장 로직으로 `satellite_intel` 스키마와 연동됩니다.

- 입력은 로컬 업로드가 아니라 **`original_image/` 원본 풀에서 선택**합니다. **파일명이 곧 메타데이터**입니다. 형식: `자산명_지역명_지역ID_센서_YYYY-MM-DD HHMMSS.확장자`
  - 예: `425-1_개풍군_1_SAR_2026-07-09 100000.tif`, `426-2_원산시_2_EO_2026-06-01 100000.png`
  - 파일명에 `:`를 쓸 수 없어 시각은 붙여 씁니다 (`100000` = 10:00:00, 자리수가 4/6/7이어도 허용)
  - 자산명/지역명에 `_`가 들어가면 파싱에 실패하니 이름에 언더스코어를 쓰지 마세요
- **"DB 저장" 버튼** 하나로 다음을 한 번에 저장합니다:
  - `image_analysis`에 영상 메타데이터 — 처음 보는 영상은 새 행, 같은 `(자산명, 지역ID, 촬영시각, 센서)` 영상은 기존 `image_id` 재사용(덮어쓰기)
  - `detection_result`에 클래스별 집계 (편집 반영된 최종 검출목록 기준) — `created_at` = 버튼을 누른 시스템 시간
  - 박스가 그려진 결과 이미지 → `result_image/` 폴더 (원본은 이미 원본 풀에 있으므로 다시 저장하지 않음)
  - 두 테이블 저장은 하나의 트랜잭션이라 중간에 실패하면 함께 롤백됩니다
- 저장 직후 `shared/change_analysis.py`가 같은 (지역, 센서)의 직전 촬영분과 비교해 **변화 경보(alert)** 를 생성합니다. 경보는 분석 현황/지휘관 현황 지도와 경보 화면에 나타납니다.
- 모델 라벨과 `equipment.class_name`은 직접 매치됩니다. equipment에 없는 라벨(직접 추가한 박스 등)은 경고 후 저장에서 제외됩니다.
- 파일명이 형식에 안 맞으면 탐지는 정상 동작하고 DB 저장만 비활성화됩니다.

## 테스트

```powershell
python -m unittest discover tests
```

현재는 회전 좌표 변환 단위 테스트가 포함되어 있습니다.

## 새 페이지 추가 방법

1. `features/<도메인>/` 폴더를 만들고 `view.py`(화면)를 작성합니다. 추론·조회 로직이 있다면 `service.py`로 분리합니다.
2. `app.py`에서 `render_<도메인>_page`를 import하고, 역할에 맞는 `visible_pages`(상단 메뉴 노출) 또는 `hidden_pages`(숨김 — `st.switch_page`로만 진입)에 `st.Page(...)`로 등록합니다.
3. 여러 페이지가 함께 쓰는 기능이 생기면 그때 `shared/`로 옮깁니다 (처음부터 shared에 두지 않기).
