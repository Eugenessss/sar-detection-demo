# 경보 상세 화면 (features/HQ_DESK) 작업 정리

청출어람 프로젝트의 "한반도 EO 위성 지도 → 경보 상세" 기능 구현 내역 정리.

## 파일 구성

- `features/HQ_DESK/service.py` — DB 조회 · EO 지도 생성 등 로직 모음 (지도/상세 화면 공용)
- `features/HQ_DESK/view.py` — 한반도 위성 지도 화면. `render_hq_desk_page()`가 진입점이며 `app.py`의 상단 메뉴("HQ Desk")에 연결되어 있음
- `features/HQ_DESK/detail_view.py` — 마커 클릭 시 나오는 경보 상세 화면

## 1. 지도 화면 (view.py)

- Google Earth Engine(Sentinel-2 true color) 배경 위에, DB `alert` 테이블에서 조회한 **지역(region)별 가장 최신 경보 1건씩**을 마커로 표시 (지역이 여러 곳이면 마커도 여러 개).
- 마커 색상은 경보수준(`alert_level`)에 따라 다름: 🔴 긴급(URGENT) · 🟠 중요(IMPORTANT) · 🔵 특이(NOTICE).
- 마커에는 툴팁만 있고 팝업(클릭 시 텍스트박스)은 없음.
- 마커를 클릭하면 `st.session_state["view"] = "detail"`로 전환되어 상세 화면으로 이동. `app.py` 메뉴에는 지도 화면("HQ Desk")만 노출되고, 상세 화면은 같은 페이지 안에서 세션 상태로만 전환되는 "숨겨진" 화면.
- 상세 화면에서 "← 지도로 돌아가기"를 누르면 지도 컴포넌트의 `key`를 바꿔(`_map_reset_token` 증가) 다시 그리므로, 같은 마커를 재클릭해도 정상적으로 상세 화면 전환이 동작함 (이전엔 좌표 기반 dedup 로직 때문에 재클릭이 씹히는 버그가 있었음 → 수정).
- 지도 `use_container_width=True`로 폭 전체 사용 (레이아웃은 `app.py`가 전역으로 `layout="wide"` 설정).

## 2. 경보 상세 화면 (detail_view.py)

### 레이아웃 (최종본)

페이지를 **3 : 4 : 3** 비율의 3칸으로 분할:

| 왼쪽 (3) | 가운데 (4) | 오른쪽 (3) |
|---|---|---|
| 적군 자산 정보 카드 | 위성사진 (시간 선택) | 아군 자산 위치 지도 |

- 상단 제목("경보 상세")과 `alert_id` 캡션은 최종적으로 제거 (화면 위 여백을 줄이기 위해).
- 페이지 상단 padding은 CSS로 축소하되, Streamlit 툴바에 "← 지도로 돌아가기" 버튼이 가리지 않도록 `3rem` 정도 유지.

### 왼쪽 (3) — 적군 자산 정보

- `alert` + `change_event` + `image_analysis` + `region` + `equipment` 조인 결과(`service.Alert`)를 그대로 사용.
- 표시 항목: 경보수준(색상 뱃지) · 제목 · 변화 요약(`alert.message`) · 지역(`region.region_name`) · 적군 장비 정보(`equipment.class_name` / `category` / `threat_level` / `description`).
- 원래는 페이지 상단에 가로 한 줄(경보정보 · 변화요약 · 지역)로 배치했다가, 3:4:3 레이아웃으로 바뀌면서 왼쪽 세로 카드 형태로 이동.

### 가운데 (4) — 위성사진

- 시간 선택 UI: `[H-4] / [H-2] / [H-Hour]` 3개 버튼 (처음엔 실제 시각 "10:00/12:00/14:00" 라벨이었다가 요청으로 상대 시간 라벨로 변경).
  - `st.button` 3개로 직접 만들었다가 "한 번 눌러야 색이 다음 클릭에야 반영되는" 딜레이 버그가 있어서 `st.segmented_control`로 교체 (위젯이 선택 상태를 직접 관리해서 즉시 반영됨).
  - `@st.fragment`로 감싸서, 시간 버튼을 눌러도 오른쪽 지도(전체 rerun 시 매번 새로 로딩되던 EO 지도)는 다시 그려지지 않도록 함 — 버튼 클릭 시 지도가 로딩 스피너 뜨는 문제 해결.
- 사진은 원본이 정확히 **840×840 정사각형**이라, 여러 차례 시행착오 끝에 다음 방식으로 정착:
  - `st.image(width=...)` → 정사각형이 늘어나며 세로가 너무 커져 스크롤 발생 → 실패
  - `object-fit: cover` (고정 높이, 폭 100%) → 좌우/상하가 부자연스럽게 잘림 → 실패
  - `object-fit: contain` (정사각형 유지, 레터박스) → 잘리진 않지만 좌우에 빈 여백(검은 바) 생김 → "풀 스크린샷 느낌"이 아니라서 반려
  - **최종**: 로컬 이미지 파일을 base64 data URI로 인코딩해 `<img>` 태그로 직접 렌더링. 박스 높이를 오른쪽 지도와 **동일한 고정값(480px)** 으로 맞추고 `object-fit: cover`로 폭을 꽉 채움. 오른쪽 지도 캡션 아래에 44px 여백을 넣어서 사진 박스와 지도 박스의 위/아래 끝이 나란히 정렬되도록 함.

### 오른쪽 (3) — 아군 자산 위치

- 왼쪽 지도와 동일한 EO 배경(`build_eo_map()` 공용 함수) 위에, **`strike_asset` DB 테이블**(실제 아군 타격 자산: F-15K, K9A1, 천무 등)을 조회해 마커로 표시.
  - 처음엔 목업 데이터(3개 가짜 부대)로 틀만 만들었다가, `satellite_intel_strike_asset.sql` 스키마를 참고해 실제 DB 조회로 교체.
- 마커를 클릭하면 페이지 이동 없이 지도 바로 아래 정보 패널에 부대명 · 자산명 · 종류 · 사거리 · 대응시간 · 위치를 표시.
- 지도 높이는 왼쪽 사진 박스와 동일한 480px로 통일.

## 3. service.py — DB 연동 정리

### 경보(Alert) 조회

FK 체인: `alert.change_id → change_event.change_id`, `change_event.current_image_id → image_analysis.image_id`, `image_analysis.region_id → region.region_id` (위도·경도), `change_event.equipment_id → equipment.equipment_id` (적군 장비).

- `get_alerts()` — 지도에 표시할 경보를 **지역(region_id)별로 가장 최신 것 1건씩** 조회 (`ROW_NUMBER() OVER (PARTITION BY region_id ORDER BY created_at DESC) = 1`). region마다 "최신 1건" 규칙 자체는 기존과 동일하고, 대상만 전체 → 지역별로 나뉨.
- `get_alert_by_id(alert_id)` — 상세 화면용 단건 조회.
- `Alert` dataclass에 적군 장비 관련 필드(`asset_category`, `asset_threat_level`, `asset_description`)를 추가해 `equipment` 테이블 정보까지 함께 반환.

### 위성사진 조회

- `get_alert_images(alert_id)` — **`alert → change_event → image_analysis`** 조인으로, `current_image`와 같은 지역(`region_id`)에서 촬영된 사진들 중 `result_image_path`가 채워진 것만 최신 3장(2시간 간격 = H-4/H-2/H-Hour)을 가져옴.
  - 다만 현재 시드 데이터의 `change_event`는 아직 실제 사진(`image_id` 8199번대)에 연결되어 있지 않아서, DB 조회 결과가 0건이면 프로젝트 루트 `result_image/` 폴더를 직접 스캔하는 방식으로 **자동 대체(fallback)** 하도록 처리. (`change_event`가 실제 사진에 연결되면 자동으로 DB 조회 경로를 타게 됨)
  - `image_time_label(path)` — 파일명 끝 `HHMMSS`를 `HH:MM` 라벨로 변환.

### EO 배경 지도

- `build_eo_map()` — Sentinel-2(`COPERNICUS/S2_SR`) true color 레이어를 올린 folium 지도 생성 함수. 지도 화면과 상세 화면(아군 자산 지도) 양쪽에서 공용으로 사용.
- Leaflet의 레이어 선택 팝업(`folium.LayerControl`)은 불필요한 UI라 제거.

### 아군 타격 자산

- `get_strike_assets()` — `strike_asset` 테이블 조회 (`asset_name`, `name`, `category`, `range_km`, `response_time_min`, `notes`, `location_name`, `latitude`, `longitude`).

## 4. 알려진 이슈 / 후속 작업

- 현재 seed된 `alert` 1~16번은 `change_event.previous_image_id / current_image_id`가 대량 생성된 더미 `image_analysis` row(빈 경로)를 가리키고 있어서, 실제 사진(8199번대)과는 DB상 연결이 안 되어 있음. 지금은 폴더 스캔 fallback으로 데모가 동작하지만, **`change_event`가 실제 이미지에 연결되면** 코드 수정 없이 자동으로 DB 조회 결과를 사용하게 됨.
- 환경 이슈: 로컬에 Python 인터프리터가 여러 개(`miniconda3\envs\streamlit`, `Python312`) 있어서 패키지 설치 시 실제 실행되는 인터프리터를 확인하고 설치해야 함.

## 5. 아군 자산: strike_asset → ally_asset 교체 + 사거리 필터 + 타격반경 원 (신규)

오른쪽(3) "아군 자산 위치" 패널을 `strike_asset`(부대당 1행) 대신 `ally_asset`(부대+장비+무장
조합당 1행, `features/commander/ally_asset.sql` 참고)을 쓰도록 교체하고, 적군까지 거리를
계산해 사거리를 만족하는 무장만 선택할 수 있게 하고, 선택한 무장의 타격반경을 가운데 사진에
원으로 겹쳐 그리는 기능을 추가했다.

### service.py

- `AllyAsset` 데이터클래스(`get_ally_assets()`)로 `ally_asset` 테이블 전체(부대명·장비명·
  종류·무장명·사거리·타격반경(`effect_radius_m`)·좌표 등)를 조회.
- `haversine_km()` — 위경도 두 점의 직선거리(km) 계산 (지구 반지름 6371.0088km 기준).
- `evaluate_ally_assets(assets, enemy_lat, enemy_lon)` — 각 자산에 적군(경보) 위치까지의
  `distance_km`과, `range_km >= distance_km`인지(`in_range`)를 채워 넣는다. 적군 위치는
  `alert`에 이미 조인되어 있는 `region.latitude/longitude`(=`Alert.latitude/longitude`)를
  그대로 쓴다 (별도 조회 불필요).
- `group_ally_units(assets)` — 같은 부대의 여러 무장(행)을 지도 마커 1개로 묶기 위한 헬퍼.
- 기존 `FriendlyAsset`/`get_strike_assets()`/`_STRIKE_ASSET_QUERY`는 제거하고 위 함수들로 대체.

### detail_view.py

- 오른쪽 지도: 부대 단위로 마커 1개만 표시(무장 옵션 수만큼 중복 X). 마커를 클릭하면
  `st.session_state["hq_selected_unit"]`에 부대명을 저장하고, 그 부대의 무장 옵션들을
  체크박스 목록으로 보여준다.
  - `in_range`(사거리 충족)인 옵션만 체크 가능. 사거리 밖인 옵션은 비활성화(disabled) 표시.
  - 체크 상태는 경보(`alert_id`)별로 `st.session_state[f"hq_selected_munitions_{alert_id}"]`
    (asset_id 집합)에 저장 → 경보를 바꾸면 선택이 초기화된다.
- 가운데 사진: 체크된 무장 옵션마다 `effect_radius_m`(타격반경, m)을 반지름으로 하는 원을
  사진 정중앙에 겹쳐 그린다(옵션별로 색을 다르게 순환). `effect_radius_m`이 없는 옵션(예:
  대전차고폭탄·130mm·600mm탄도미사일 — 공개 자료 없음)은 원 없이 범례에만 "타격반경 정보
  없음"으로 표시.
  - (2026-07 갱신: 아래 6번 항목에서 "원본 840×840 고정" 가정을 걷어내고 사진 크기가
    제각각이어도 되도록 다시 바꿈. 아래 6번이 최신 내용.)

## 6. 사진 원본 크기 출력 + 1px=1m + 무장별 무작위 다중 원 (신규)

팀원 쪽에서 사진 파이프라인이 바뀌어 위성사진 크기가 더 이상 840×840 고정이 아니게 됨에
따라, 5번 항목의 "정사각형 480px 고정 + 1km 가정" 방식을 걷어내고 다음으로 교체했다.

### 사진을 원본 비율 그대로 출력 (detail_view.py)

- 사진 박스를 고정 크기 대신 `<div style="aspect-ratio: 원본가로/원본세로">`로 감싸서,
  원본과 정확히 같은 비율을 유지한 채 화면 폭에 맞춰서만 축소되도록 했다 (잘림·늘어남 없음,
  `PIL.Image.open(path).size`로 원본 픽셀 크기를 읽어옴).
- 원(마커)의 위치·지름은 원본 픽셀 좌표를 **퍼센트(%)** 로 계산해서 그린다. 그래야 사진이
  화면 폭에 맞춰 축소되어도 원이 항상 사진과 같은 비율로 따라 움직인다(고정 px로 그리면
  사진만 줄어들고 원은 그대로라 어긋난다).
- m→px 환산은 "일단 1픽셀당 1m"로 고정(`_METERS_PER_PIXEL = 1.0`). 실제 GSD가 확인되면
  이 값만 바꾸면 된다. (기존 "840px=1km" 가정은 제거)

### 무장별 무작위 다중 원 (detail_view.py `_circle_count_for` / `_circle_centers`)

요청에 따라 무장(또는 자산 종류)마다 그리는 원의 개수를 다르게 했다. 그 외 무장은 기존처럼
사진 정중앙에 1개만 그린다.

| 무장 / 종류 | 원 개수 |
| --- | --- |
| 집속탄 (`munition_name`) | 200개 |
| 130mm 무유도미사일 (`munition_name`) | 12개 |
| 자주곡사포 (`category`, 예: K9A1) | 6개 |
| 그 외 | 1개 (중앙) |

여러 개일 때 중심 좌표는 사진 범위 안에서 무작위로 뽑되(`random.Random(seed)`), seed를
`(alert_id, asset_id)`로 고정해서 같은 경보·같은 자산이면 다시 그려도(rerun) 항상 같은
배치가 나오게 했다(매번 위치가 흔들리며 다시 찍히는 것 방지). 경보가 다르면 다른 배치가
나온다.

### 체크 즉시 원이 표시되지 않던 버그 수정

원인: 컬럼 순서상 가운데(사진)를 오른쪽(체크박스)보다 먼저 그리는데, 체크박스 클릭으로
바뀐 selection 값 반영이 체크박스를 실제로 그리는 코드(오른쪽 패널) 안에서만 일어나서,
그 앞에서 이미 그려진 사진은 "클릭 전" 상태로 보였다(다음 rerun에야 반영).

수정: `render_alert_detail_page()`에서 컬럼을 나누기 전에 `_sync_selected_munitions()`를
먼저 호출해, `st.session_state[위젯key]`(Streamlit이 rerun 시작 시점에 이미 최신 클릭
결과로 갱신해 둔 값)를 읽어 selection set에 미리 반영한다. 그 다음에 계산하는
`selected_assets`가 이미 최신 상태이므로, 사진에 바로 원이 나타난다.

## 7. 적군 위치 표시 + 타격/대기 버튼 + commander_decision 로그 (신규)

아군 자산을 선택한 뒤 실제로 "타격"할지 "대기"할지 지휘관이 결심하고, 그 결심을
`commander_decision` 테이블에 기록 → 화면 하단에 로그로 보여주는 기능을 추가했다.

### 적군 위치를 아군 자산 지도에도 표시 (detail_view.py `_render_friendly_asset_panel`)

- 기존 기능(부대 마커 클릭 → 무장 옵션 체크박스)은 그대로 두고, 같은 지도에 적군 위치
  마커를 하나 더 찍는다. 색상은 경보 지도와 같은 규칙(`service.marker_color(alert_level)`
  — 🔴 긴급/🟠 중요/🔵 특이)을 그대로 써서 위험도를 지도만 봐도 알 수 있게 했다.

### commander_decision 저장 로직 (service.py)

- `why_text_for_munition(munition_name)` — 요청받은 규칙 그대로 매핑:
  `KGGB 유도폭탄`/`600mm 탄도미사일` → `[상세 타격 필요]`, `집속탄`/`이중목적고폭탄`/
  `130mm 무유도미사일`(또는 이름에 "무유도미사일" 포함) → `[넓은 면적 타격 필요]`,
  `대전차고폭탄` → `[기갑표적 타격 필요]`. 목록에 없는 새 무장이 추가될 경우를 대비해
  기본값으로 `[타격 필요]`를 반환한다(안전장치, 요청엔 없던 값이라 새 무장 발견 시
  이 텍스트가 나오면 규칙을 더 추가해야 한다는 신호로 보면 된다).
- `save_commander_decision(commander_id, who_text, when_text, where_text, what_text, how_text, why_text, created_at)`
  — `commander_decision` 테이블에 1행 INSERT. `report_id`는 테이블의 자동증가 기본키라고
  가정하고 INSERT에 넣지 않는다(테이블은 이미 존재한다는 전제이며 새로 만들지 않음).
- `get_recent_commander_decisions(limit=20)` — 최신순으로 로그를 조회(하단 표 표시용).

### 타격/대기 버튼 UI + 하단 로그 표 (detail_view.py)

- `_render_decision_actions(alert, selected_assets)` — 3칸 레이아웃 아래(전체 폭)에 배치.
  선택된 무장 옵션이 없으면 안내만 표시. 있으면 지휘관 ID 입력칸(로그인 기능이 없어 직접
  입력, `st.number_input`)과 "🎯 타격"/"⏸ 대기" 버튼 두 개를 보여준다.
  - 필드 매핑: `when_text`=`alert.detected_at`(탐지시각), `where_text`=`alert.region`+좌표,
    `how_text`=선택한 자산의 `platform_name·munition_name`, `why_text`=
    `why_text_for_munition(munition_name)`. 체크된 옵션이 여러 개면 옵션마다 한 행씩 기록.
  - **who_text(적군 부대명)**: DB에 부대명 컬럼이 따로 없어서, `service.get_latest_detected_region_name()`
    (image_analysis에서 `created_at`이 가장 최신인 행의 `region_id` → `region.region_name`)
    값을 대신 쓴다. 조회 실패 시 `alert.region`으로 대체한다.
  - `what_text`(적군 장비)는 적군 장비 종류(`alert.asset_category`)를 그대로 쓴다.
  - "⏸ 대기" 버튼은 요청대로 `how_text`/`why_text`만 `[대기]`로 남기고 나머지(누구/언제/
    어디서/무엇을)는 타격 버튼과 동일한 값으로 기록한다.
  - `created_at`은 버튼을 누른 시각(`datetime.now()`).
- `_render_decision_log()` — `get_recent_commander_decisions()` 결과를 `st.dataframe`으로
  페이지 맨 아래에 표시.
- `report_id`가 실제로 자동증가 기본키인지, `commander_decision` 테이블 스키마가 위 컬럼
  구성과 정확히 일치하는지는 샌드박스에서 DB에 직접 연결할 수 없어 확인하지 못했다 — 만약
  INSERT가 스키마 불일치로 실패하면 화면에 `st.error`로 에러 메시지가 그대로 표시된다.
