# change_analysis.py 초심자 설명

`change_analysis.py`는 탐지 결과가 DB에 저장된 뒤, 이전 영상과 현재 영상을 비교해서 경보를 만드는 파일입니다.

한 줄로 말하면:

```text
detection_result 비교 -> change_event 생성 -> alert 생성
```

## 언제 실행되나요?

EO/SAR 화면에서 이미지 탐지가 끝나고 `detection_result` 저장이 성공하면 실행됩니다.

흐름은 아래와 같습니다.

```text
1. 이미지 탐지
2. 탐지된 장비명을 equipment_id로 변환
3. detection_result 테이블에 현재 이미지의 장비 수량 저장
4. analyze_image_change(image_id) 호출
5. 이전 이미지와 현재 이미지를 비교
6. change_event 테이블에 변화 기록
7. alert 테이블에 경보 메시지 생성
```

## 가장 중요한 함수

```python
analyze_image_change(image_id: int) -> ChangeAnalysisOutcome
```

이 함수 하나가 변화 분석의 시작점입니다.

`image_id`는 `image_analysis` 테이블의 이미지 번호입니다. 예를 들어 업로드 파일명이 `8192.tif`이면, 이 앱은 `8192`를 `image_id`로 사용합니다.

## 사용하는 주요 테이블

| 테이블 | 역할 |
| --- | --- |
| `image_analysis` | 이미지의 자산명, 지역명, 촬영시각을 찾습니다. |
| `detection_result` | 이미지별 장비 수량을 읽습니다. |
| `equipment` | 장비명, equipment_id, threat_level을 읽습니다. |
| `change_event` | 이전 이미지와 현재 이미지의 수량 차이를 저장합니다. |
| `alert` | 실제 경보 메시지를 저장합니다. |

## 전체 처리 순서

### 1. 현재 이미지 정보 조회

먼저 `image_analysis`에서 현재 `image_id`의 정보를 가져옵니다.

필요한 값은 다음입니다. (직전 이미지를 찾는 데 쓰는 3개만 조회합니다.)

```text
asset_name
region_name
captured_time
```

이 정보가 없으면 비교할 수 없으므로 오류를 냅니다.

### 2. 직전 이미지 찾기

같은 자산, 같은 지역에서 현재 이미지보다 촬영시각이 빠른 이미지 중 가장 최근 이미지를 찾습니다.

기준은 아래와 같습니다.

```text
같은 asset_name
같은 region_name
captured_time이 현재보다 이전
가장 최근 촬영시각 1개
```

직전 이미지가 없으면 최초 영상으로 보고 경보를 만들지 않습니다.

### 3. 기존 분석 로그는 지우지 않습니다 (append-only)

같은 현재 이미지에 대해 이미 만들어진 `change_event`와 `alert`는 그대로 둡니다. 아무것도 삭제하지 않습니다.

사용자가 박스를 수정하거나 라벨을 고친 뒤 다시 저장하면, 같은 (이전 이미지, 현재 이미지, 장비) 조합의 **마지막 로그**와 수량을 비교해서:

```text
마지막 로그와 수량이 같다  -> 아무것도 추가하지 않음 (같은 내용을 또 기록하지 않음)
마지막 로그와 수량이 다르다 -> '[수정] ...' 표시가 붙은 새 로그를 추가
아예 처음 보는 장비다      -> 일반 로그를 추가
```

이렇게 하면 판독관이 언제 무엇을 어떻게 고쳤는지가 로그로 전부 남고, 이미 확인 처리(`CHECKED`)한 경보도 사라지지 않습니다.

### 4. 변화 이벤트 생성

이전 이미지와 현재 이미지의 `detection_result`를 장비별로 비교합니다.

예시는 아래와 같습니다.

| 장비 | 이전 수량 | 현재 수량 | event_type | delta_count |
| --- | ---: | ---: | --- | ---: |
| T72 | 0 | 3 | `NEW` | 3 |
| BMP2 | 5 | 12 | `INCREASED` | 7 |
| Truck | 10 | 4 | `DECREASED` | -6 |
| ZIL131 | 2 | 0 | `DISAPPEARED` | -2 |

수량이 같으면 `change_event`를 만들지 않습니다.

생성된 개수(`events_created`)는 별도 COUNT 쿼리 없이 INSERT 결과의 처리 행 수(rowcount)에서 바로 얻습니다.

### 5. 경보 생성

`change_event`가 만들어진 뒤, SQL 규칙으로 `alert`를 생성합니다.

규칙은 `equipment.threat_level`과 `change_event.delta_count`를 사용합니다.

| 경보 | 조건 | 의미 |
| --- | --- | --- |
| `URGENT` | `threat_level = 1` | 고가치 표적은 변화가 있으면 무조건 긴급 |
| `IMPORTANT` | `threat_level = 2` and `ABS(delta_count) >= 10` | 중요 장비가 10대 이상 변동 |
| `NOTICE` | `threat_level = 3` and `delta_count >= 20` | 기타 장비가 20대 이상 증가 |

중복 방지는 `NOT EXISTS` 조건이 담당합니다. 이미 경보가 발행된 change_event는 건너뛰고, 아직 경보가 없는 이벤트에만 새로 발행합니다. 기존 로그를 지우지 않는 append-only 방식이라 이 조건이 꼭 필요합니다.

주의할 점:

`equipment_id`는 장비를 구분하는 번호입니다. 경보 등급을 직접 뜻하지 않습니다. 경보 등급은 `equipment.threat_level`로 판단합니다.

## 반환값

`analyze_image_change()`는 `ChangeAnalysisOutcome`을 반환합니다.

```python
ChangeAnalysisOutcome(
    image_id=현재 이미지 ID,
    previous_image_id=직전 이미지 ID,
    events_created=생성된 change_event 개수,
    alerts_created=이번 실행에서 새로 발행된 alert 목록,   # 각 원소는 {"alert_level": ..., "title": ...} 두 키만 담습니다
    replaced_previous_analysis=기존 로그가 있는 상태에서 실행됐는지 (수정 기록인지) 여부,
)
```

`events_created`와 `alerts_created`는 **이번 실행에서 새로 추가된 것만** 셉니다. 예전에 만들어진 로그와 경보는 포함하지 않습니다.

화면에서는 이 값을 보고 사용자에게 아래처럼 알려줍니다.

```text
변화 이벤트 3건, 경보 1건 생성
[URGENT] T72 표적 수량 변화
```

## 아주 작은 예시

이전 이미지의 탐지 결과:

```text
T72: 0대
Truck: 5대
```

현재 이미지의 탐지 결과:

```text
T72: 2대
Truck: 5대
```

결과:

```text
T72는 0대에서 2대로 증가 -> change_event 생성
Truck은 5대에서 5대로 동일 -> 아무것도 생성하지 않음
T72의 threat_level이 1이면 -> alert에 URGENT 생성
```

## 기억할 것

- 이 파일은 객체 탐지를 직접 하지 않습니다.
- 이 파일은 이미 저장된 `detection_result`를 비교합니다.
- 변화 기록은 `change_event`에 저장합니다.
- 실제 경보 메시지는 `alert`에 저장합니다.
- 기존 로그와 경보는 절대 지우지 않습니다. 다시 분석하면 수량이 달라진 장비만 `[수정]` 로그로 추가되고, 같은 내용의 재분석은 아무것도 만들지 않습니다.
