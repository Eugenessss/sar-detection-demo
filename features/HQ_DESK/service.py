"""
[경보 지도 - 서비스]
alert_id로 조회되는 경보 세션(위치정보·적군자산·경보수준 등)을 실제 DB(satellite_intel)에서
조회해 지도에 필요한 값(위도·경도·경보수준·제목·변화요약·지역)으로 정리하는 함수 모음.

연결 경로 (FK):
  alert.change_id -> change_event.change_id
  change_event.current_image_id -> image_analysis.image_id
  image_analysis.region_id -> region.region_id   (위도·경도는 region 테이블에 있다)
  change_event.equipment_id -> equipment.equipment_id (적군자산 이름)

위성사진은 alert.change_id -> change_event.current_image_id -> image_analysis 순서로
조인해서, 같은 지역(region_id)·같은 센서에서 촬영된 최근 사진들 중 result_image_path가
채워진 것만 최신 3장(H-4/H-2/H-Hour) 골라 온다. 파일이 이 PC에 없는 행(다른 팀원
PC에서 저장된 영상)은 제외되며, 대체 표시는 하지 않는다 — 경보와 무관한 사진이
시각 라벨을 달고 나오면 지휘 판단을 오도하므로, 없으면 빈 슬롯으로 보여준다.
(과거에는 result_image/ 폴더 전체를 훑는 fallback이 있었으나 이 이유로 제거됨.)

지도(EO 위성 배경) 생성 로직은 view.py·detail_view.py가 똑같이 쓰므로 build_eo_map()
하나로 공용화했다. 아군 자산(아군 타격 자산)은 ally_asset 테이블(부대+장비+무장 조합별
사거리·타격반경)에서 조회하고, 적군 위치(alert에 이미 조인된 region 좌표)까지의
직선거리를 하버사인 공식으로 계산해 사거리 충족 여부를 판정한다.
"""
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional

import ee
import folium
from sqlalchemy import text

from shared import s3_store
from shared.database import get_engine

_DB = "satellite_intel"

# DB에 저장된 alert_level(enum) 값 -> 화면 표시용 한글/색상 매핑
ALERT_LEVEL_LABELS = {
    "URGENT": "긴급",
    "IMPORTANT": "중요",
    "NOTICE": "특이",
}
ALERT_LEVEL_COLORS = {
    "URGENT": "red",
    "IMPORTANT": "orange",
    "NOTICE": "blue",
}
DEFAULT_MARKER_COLOR = "gray"  # 알 수 없는 경보수준이 들어와도 지도가 깨지지 않도록

# 지도에는 전체 경보 이력이 아니라, 지역(region)별로 가장 최근에 생성된 경보
# 1건씩만 표시한다. (예: 개성시·원산시에 각각 경보가 여러 건 있어도, 지역마다
# 최신 1건씩만 가져온다.)

# 프로젝트 루트 (result_image_path 같은 DB의 상대경로를 실제 파일로 바꿀 때 기준 폴더).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

MAX_IMAGES_PER_ALERT = 3

# alert -> change_event -> image_analysis -> region / equipment 순서로 조인해
# 지도에 필요한 값을 한 번에 가져온다. region_id가 없는 image는 자동으로 제외된다.
# region_id·created_at은 지역별 최신 1건을 가리는 데(_LATEST_ALERTS_PER_REGION_QUERY)
# 쓰인다.
_ALERT_QUERY = f"""
    SELECT
        a.alert_id, a.alert_level, a.title, a.message, a.created_at,
        ia.sensor_type,
        eq.class_name, eq.category AS eq_category, eq.threat_level, eq.description AS eq_description,
        r.region_id, r.region_name, r.latitude, r.longitude
    FROM `{_DB}`.`alert` a
    JOIN `{_DB}`.`change_event` ce ON a.change_id = ce.change_id
    JOIN `{_DB}`.`image_analysis` ia ON ce.current_image_id = ia.image_id
    JOIN `{_DB}`.`region` r ON ia.region_id = r.region_id
    JOIN `{_DB}`.`equipment` eq ON ce.equipment_id = eq.equipment_id
"""

# region_id로 파티션을 나눠 alert.created_at이 가장 최근인 1건만 남긴다
# (region마다 "최신 경보 1건" 규칙은 그대로이고, 대상이 지역별로 나뉜 것뿐).
# {where}에는 센서 필터("WHERE ranked.sensor_type = :sensor")가 들어갈 수 있다 —
# WHERE는 ROW_NUMBER보다 먼저 적용되므로, 필터 후 남은 경보 중 지역별 최신 1건이 뽑힌다.
_LATEST_ALERTS_PER_REGION_QUERY = f"""
    SELECT * FROM (
        SELECT ranked.*,
               ROW_NUMBER() OVER (
                   PARTITION BY ranked.region_id
                   ORDER BY ranked.created_at DESC, ranked.alert_id DESC
               ) AS rn
        FROM ({_ALERT_QUERY}) ranked
        {{where}}
    ) t
    WHERE rn = 1
    ORDER BY created_at DESC
"""


@dataclass
class Alert:
    """alert_id 세션 하나를 담은 것 (위치정보·적군자산·경보수준·제목 등)."""
    alert_id: int
    latitude: float
    longitude: float
    alert_level: str       # DB enum 원본값 (URGENT/IMPORTANT/NOTICE)
    sensor_type: str = ""  # 경보 기준 영상의 센서 (EO/SAR)
    asset_name: str = ""   # 적군자산(장비) 이름 (equipment.class_name)
    asset_category: str = ""       # 적군자산 종류 (equipment.category)
    asset_threat_level: Optional[int] = None  # 적군자산 위협도 (equipment.threat_level)
    asset_description: str = ""    # 적군자산 설명 (equipment.description)
    title: str = ""        # 경보제목
    summary: str = ""      # 변화요약(경보 발생 근거)
    region: str = ""       # 지역
    region_id: Optional[int] = None  # 지역 ID (상세 화면의 센서 전환에 사용)
    detected_at: Optional[datetime] = None  # 경보(변화) 탐지 시각 (alert.created_at)


def _row_to_alert(row) -> Alert:
    m = dict(row._mapping)
    return Alert(
        alert_id=m["alert_id"],
        latitude=float(m["latitude"]),
        longitude=float(m["longitude"]),
        alert_level=m["alert_level"],
        sensor_type=m["sensor_type"] or "",
        asset_name=m["class_name"] or "",
        asset_category=m["eq_category"] or "",
        asset_threat_level=m["threat_level"],
        asset_description=m["eq_description"] or "",
        title=m["title"] or "",
        summary=m["message"] or "",
        region=m["region_name"] or "",
        region_id=int(m["region_id"]) if m["region_id"] is not None else None,
        detected_at=m.get("created_at"),
    )


def get_alerts(sensor: Optional[str] = None) -> List[Alert]:
    """지도에 표시할 경보 목록을 지역(region)별로 가장 최근 것 1건씩 조회한다.

    sensor("EO"/"SAR")를 주면 그 센서의 경보만 대상으로 지역별 최신 1건을 고른다
    (None이면 센서 무관 최신 1건 — 기존 동작).
    """
    where = "WHERE ranked.sensor_type = :sensor" if sensor else ""
    params = {"sensor": sensor} if sensor else {}
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(_LATEST_ALERTS_PER_REGION_QUERY.format(where=where)), params
        )
        return [_row_to_alert(row) for row in rows]


def get_latest_alert_id(region_id: int, sensor: str) -> Optional[int]:
    """해당 지역·센서의 최신 경보 alert_id를 돌려준다 (없으면 None).

    상세 화면의 센서 전환용 — 지도의 "지역별 최신 1건" 규칙과 같은 기준
    (created_at 최신, 동률이면 alert_id 큰 것)을 쓴다.
    """
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT a.alert_id "
                f"FROM `{_DB}`.`alert` a "
                f"JOIN `{_DB}`.`change_event` ce ON a.change_id = ce.change_id "
                f"JOIN `{_DB}`.`image_analysis` ia ON ce.current_image_id = ia.image_id "
                "WHERE ia.region_id = :region_id AND ia.sensor_type = :sensor "
                "ORDER BY a.created_at DESC, a.alert_id DESC LIMIT 1"
            ),
            {"region_id": region_id, "sensor": sensor},
        ).fetchone()
    return int(row[0]) if row else None


def get_alert_by_id(alert_id: int) -> Optional[Alert]:
    """alert_id 하나에 해당하는 경보를 DB에서 조회한다 (없으면 None)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(_ALERT_QUERY + " WHERE a.alert_id = :alert_id"),
            {"alert_id": alert_id},
        ).fetchone()
    return _row_to_alert(row) if row else None


# alert -> change_event -> (current_image의) region_id로, 같은 지역·같은 센서에서
# 촬영된 사진들 중 result_image_path가 채워진 것만, current_image 시각 이전(포함)으로
# 최신 3장을 가져온다. 2시간 간격 촬영이므로 이 3장이 각각 H-4/H-2/H-Hour에 해당한다.
# 센서를 맞추는 이유: SAR/EO는 영상 특성과 탐지 클래스가 완전히 달라, EO 경보의
# 시계열 사이에 SAR 사진이 끼면 비교 흐름이 끊긴다 (변화 분석의 비교 키와 동일 기준).
_ALERT_IMAGES_QUERY = f"""
    SELECT ia2.result_image_path, ia2.original_image_path, ia2.captured_time
    FROM `{_DB}`.`alert` a
    JOIN `{_DB}`.`change_event` ce ON a.change_id = ce.change_id
    JOIN `{_DB}`.`image_analysis` ia ON ce.current_image_id = ia.image_id
    JOIN `{_DB}`.`image_analysis` ia2 ON ia2.region_id = ia.region_id
                                     AND ia2.sensor_type = ia.sensor_type
    WHERE a.alert_id = :alert_id
      AND ia2.captured_time <= ia.captured_time
      AND ia2.result_image_path IS NOT NULL
      AND ia2.result_image_path <> ''
    ORDER BY ia2.captured_time DESC
    LIMIT {MAX_IMAGES_PER_ALERT}
"""


def get_alert_images(alert_id: int) -> List[Path]:
    """alert -> change_event -> image_analysis로 조인해 result_image_path를 가져온다.

    로컬에 없는 파일은 S3에서 내려받아 채운다 (다른 팀원 PC에서 저장된 영상 공유).
    그래도 없는 사진은 다른 것으로 채우지 않는다 — 경보와 무관한 사진이 시각 라벨을
    달고 보이면 오도하기 때문. 화면은 빈 슬롯을 "이미지 없음"으로 표시한다.
    """
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(_ALERT_IMAGES_QUERY),
            {"alert_id": alert_id},
        ).fetchall()

    images: List[Path] = []
    for row in reversed(rows):  # DESC로 가져왔으니 오래된 순으로 다시 뒤집는다.
        m = dict(row._mapping)
        rel_path = m["result_image_path"] or m["original_image_path"]
        full_path = s3_store.ensure_local(rel_path)
        if full_path is not None:
            images.append(full_path)

    return images[:MAX_IMAGES_PER_ALERT]


def marker_color(alert_level: str) -> str:
    """경보수준(enum) 문자열을 folium 마커 색상 이름으로 바꾼다."""
    return ALERT_LEVEL_COLORS.get(alert_level, DEFAULT_MARKER_COLOR)


def marker_label(alert_level: str) -> str:
    """경보수준(enum) 문자열을 화면 표시용 한글(긴급/중요/특이)로 바꾼다."""
    return ALERT_LEVEL_LABELS.get(alert_level, alert_level)


# 지도를 한반도 전체가 보이도록 축소하고 나니, 기본 Leaflet 핀 마커(folium.Icon)가
# 화면 대비 너무 커 보여서 작은 원형 마커(CircleMarker)로 통일한다.
MARKER_RADIUS_PX = 8


def add_circle_marker(map_obj: folium.Map, latitude: float, longitude: float, color: str, tooltip: str) -> None:
    """작은 원형 마커 하나를 지도에 추가한다 (경보 지도·아군 자산 지도 공용)."""
    folium.CircleMarker(
        location=[latitude, longitude],
        radius=MARKER_RADIUS_PX,
        color="white",
        weight=1.5,
        fill=True,
        fill_color=color,
        fill_opacity=0.9,
        tooltip=tooltip,
    ).add_to(map_obj)


# =====================================================================
# EO 위성 배경 지도 (경보 지도 화면·경보 상세 화면 공용)
# =====================================================================

def _add_ee_layer(self, ee_image_object, vis_params, name):
    """geemap 없이 Folium에 Earth Engine 레이어를 추가하는 함수 (folium.Map에 매서드로 붙인다)."""
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Google Earth Engine',
        name=name,
        overlay=True,
        control=True,
    ).add_to(self)


folium.Map.add_ee_layer = _add_ee_layer


# 초기 화면에 한반도 전체(남한+북한)가 다 보이도록 고정하는 범위.
# 우리 시스템은 북한 동향(신의주·나선 등 북쪽 지역 포함)이 중요해서, 남한 위주로
# 잘려 보이지 않게 fit_bounds로 위/아래 범위를 강제한다.
_KOREA_PENINSULA_BOUNDS = [[33.0, 124.0], [43.2, 131.0]]  # [남서(제주 아래)], [북동(나선/신의주 위)]


def build_eo_map(location=(38.0, 127.5), zoom_start: int = 6) -> folium.Map:
    """한반도(남한+북한 전체) Sentinel-2 EO 레이어가 깔린 기본 지도를 만든다 (지도·상세 화면 공용)."""
    # GEE 초기화 (인증 안 되어있으면 터미널에 링크 뜸)
    try:
        ee.Initialize(project='project-501908')
    except Exception:
        ee.Authenticate()
        ee.Initialize(project='project-501908')

    m = folium.Map(location=list(location), zoom_start=zoom_start)
    # zoom_start만으로는 화면 비율에 따라 북한 위쪽이 잘려 보일 수 있어서,
    # 한반도 전체 범위를 명시적으로 고정한다.
    m.fit_bounds(_KOREA_PENINSULA_BOUNDS)

    dataset = ee.ImageCollection('COPERNICUS/S2_SR') \
                  .filterBounds(ee.Geometry.Point([location[1], location[0]])) \
                  .filterDate('2023-01-01', '2023-12-31') \
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10)) \
                  .median()
    vis_params = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}
    m.add_ee_layer(dataset, vis_params, 'Sentinel-2 (True Color)')
    return m


# =====================================================================
# 아군 자산 (ally_asset 테이블 - 부대+장비+무장 조합별 사거리·타격반경)
# =====================================================================
#
# strike_asset(부대당 1행)에서 ally_asset(부대+장비+무장 조합당 1행)으로 교체.
# 같은 부대·장비라도 무장(탄약)마다 사거리(range_km)·타격반경(effect_radius_m)이
# 달라서, 지도에는 부대 단위로 마커 1개만 찍고 클릭 시 그 부대가 쓸 수 있는
# 무장 옵션들을 사거리 충족 여부와 함께 보여준다.

FRIENDLY_MARKER_COLOR = "cadetblue"
FRIENDLY_MARKER_ICON = "flag"

_EARTH_RADIUS_KM = 6371.0088  # 하버사인 공식에 쓰는 지구 평균 반지름

_ALLY_ASSET_QUERY = f"""
    SELECT asset_id, unit_name, platform_name, category, munition_name,
           range_km, effect_radius_m, response_time_min, notes,
           location_name, latitude, longitude
    FROM `{_DB}`.`ally_asset`
"""


@dataclass
class AllyAsset:
    """아군 타격자산의 '부대+장비+무장' 조합 한 행.

    distance_km/in_range는 조회 직후에는 비어 있고(None), 특정 경보(적군 위치)를
    기준으로 evaluate_ally_assets()를 거쳐야 채워진다.
    """
    asset_id: int
    unit_name: str                 # 운용부대명 (예: 제1포병여단)
    platform_name: str             # 장비명 (예: K9A1)
    category: str                  # 자산 종류 (예: 자주곡사포)
    munition_name: str             # 무장/탄약 (예: 이중목적고폭탄)
    range_km: float                # 해당 무장 기준 사거리
    effect_radius_m: Optional[float]  # 명중 시 타격반경(m). 자료 없으면 None
    response_time_min: int
    notes: str = ""
    location_name: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    distance_km: Optional[float] = None   # 적군 위치까지 직선거리 (평가 전엔 None)
    in_range: Optional[bool] = None       # range_km >= distance_km 여부 (평가 전엔 None)


def _row_to_ally_asset(row) -> AllyAsset:
    m = dict(row._mapping)
    return AllyAsset(
        asset_id=int(m["asset_id"]),
        unit_name=m["unit_name"],
        platform_name=m["platform_name"],
        category=m["category"],
        munition_name=m["munition_name"],
        range_km=float(m["range_km"]),
        effect_radius_m=float(m["effect_radius_m"]) if m["effect_radius_m"] is not None else None,
        response_time_min=int(m["response_time_min"]),
        notes=m["notes"] or "",
        location_name=m["location_name"] or "",
        latitude=float(m["latitude"]),
        longitude=float(m["longitude"]),
    )


def get_ally_assets() -> List[AllyAsset]:
    """ally_asset 테이블에서 아군 타격자산(부대+장비+무장 조합) 전체를 조회한다."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(_ALLY_ASSET_QUERY))
        return [_row_to_ally_asset(row) for row in rows]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표(위도/경도, 십진도) 사이의 직선거리를 하버사인 공식으로 계산한다 (km)."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return round(2 * _EARTH_RADIUS_KM * asin(sqrt(a)), 2)


def evaluate_ally_assets(
    assets: List[AllyAsset], enemy_lat: float, enemy_lon: float,
) -> List[AllyAsset]:
    """각 자산에 적군 위치(enemy_lat, enemy_lon)까지의 거리와 사거리 충족 여부를 채운다.

    in_range는 "range_km(사거리)가 distance_km(실제 거리)를 포함하는가"
    (range_km >= distance_km)로 판정한다.
    """
    for asset in assets:
        asset.distance_km = haversine_km(enemy_lat, enemy_lon, asset.latitude, asset.longitude)
        asset.in_range = asset.range_km >= asset.distance_km
    return assets


def group_ally_units(assets: List[AllyAsset]) -> List[Dict[str, Any]]:
    """지도 마커용으로 부대(unit_name) 단위로 묶는다.

    같은 부대가 여러 무장 옵션(행)을 가지고 있어도 위치는 같으므로 마커는 1개만 찍는다.
    """
    units: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for asset in assets:
        if asset.unit_name not in units:
            units[asset.unit_name] = {
                "unit_name": asset.unit_name,
                "platform_name": asset.platform_name,
                "latitude": asset.latitude,
                "longitude": asset.longitude,
            }
            order.append(asset.unit_name)
    return [units[name] for name in order]


# =====================================================================
# 지휘관 결심 로그 (commander_decision 테이블)
# =====================================================================
#
# 상세 화면에서 아군 자산(무장 옵션)을 고른 뒤 "타격"/"대기" 버튼을 누르면
# 한 행씩 기록한다. report_id는 테이블의 AUTO_INCREMENT 기본키라고 가정하고
# INSERT에서는 지정하지 않는다 (테이블이 이미 존재한다는 전제 — 새로 만들지 않음).

# 어떤 무장이 상세 타격(정밀 점표적)이 필요한지 / 넓은 면적 타격이 필요한지 /
# 기갑표적 타격이 필요한지는 요청받은 규칙을 그대로 딕셔너리로 옮긴 것이다.
_WHY_TEXT_DETAILED_STRIKE = {"KGGB 유도폭탄", "600mm 탄도미사일"}
_WHY_TEXT_WIDE_AREA_STRIKE = {"집속탄", "이중목적고폭탄", "130mm 무유도미사일"}
_WHY_TEXT_ANTI_ARMOR_STRIKE = {"대전차고폭탄"}

WAIT_TEXT = "[대기]"


def why_text_for_munition(munition_name: str) -> str:
    """선택한 무장(munition_name)에 따라 결심 사유(why_text)를 정한다.

    - KGGB 유도폭탄 / 600mm 탄도미사일        -> [상세 타격 필요]
    - 집속탄 / 이중목적고폭탄 / 130mm 무유도미사일 -> [넓은 면적 타격 필요]
    - 대전차고폭탄                          -> [기갑표적 타격 필요]
    - 그 외(목록에 없는 새 무장 등)           -> [타격 필요] (안전한 기본값)
    """
    if munition_name in _WHY_TEXT_DETAILED_STRIKE:
        return "[상세 타격 필요]"
    if munition_name in _WHY_TEXT_WIDE_AREA_STRIKE or "무유도미사일" in munition_name:
        return "[넓은 면적 타격 필요]"
    if munition_name in _WHY_TEXT_ANTI_ARMOR_STRIKE:
        return "[기갑표적 타격 필요]"
    return "[타격 필요]"


# 적군 "부대명" 컬럼이 DB에 따로 없어서, 지휘관 결심 로그의 who_text(적군 부대명) 대신
# 값으로 "가장 최근에 탐지(분석)된 image_analysis 행의 region_id → region_name"을 쓴다.
# (요청 그대로: image_analysis에서 created_at이 가장 최신인 행의 region_id를 region
#  테이블에서 참조해 region_name을 가져온다.)
_LATEST_IMAGE_ANALYSIS_REGION_QUERY = f"""
    SELECT r.region_name
    FROM `{_DB}`.`image_analysis` ia
    JOIN `{_DB}`.`region` r ON ia.region_id = r.region_id
    ORDER BY ia.created_at DESC
    LIMIT 1
"""


def get_latest_detected_region_name() -> Optional[str]:
    """image_analysis에서 created_at이 가장 최신인 행의 region_id로 region_name을 가져온다.

    적군 "부대명" 필드가 없어, 지휘관 결심 로그의 who_text 대신 값으로 쓴다.
    """
    with get_engine().connect() as conn:
        row = conn.execute(text(_LATEST_IMAGE_ANALYSIS_REGION_QUERY)).fetchone()
    return row[0] if row else None


_INSERT_COMMANDER_DECISION = f"""
    INSERT INTO `{_DB}`.`commander_decision`
        (commander_id, who_text, when_text, where_text, what_text, how_text, why_text, created_at)
    VALUES
        (:commander_id, :who_text, :when_text, :where_text, :what_text, :how_text, :why_text, :created_at)
"""


def save_commander_decision(
    commander_id: int,
    who_text: str,
    when_text: str,
    where_text: str,
    what_text: str,
    how_text: str,
    why_text: str,
    created_at: datetime,
) -> None:
    """지휘관 결심(타격/대기) 한 건을 commander_decision 테이블에 기록한다.

    report_id는 테이블의 자동증가 기본키라고 보고 값을 지정하지 않는다.
    쓰기 작업이라 get_engine().begin()을 쓴다(성공 시 커밋, 예외 시 롤백).
    """
    with get_engine().begin() as conn:
        conn.execute(
            text(_INSERT_COMMANDER_DECISION),
            {
                "commander_id": commander_id,
                "who_text": who_text,
                "when_text": when_text,
                "where_text": where_text,
                "what_text": what_text,
                "how_text": how_text,
                "why_text": why_text,
                "created_at": created_at,
            },
        )


def get_recent_commander_decisions(limit: int = 20) -> List[Dict[str, Any]]:
    """최근 지휘관 결심 로그를 최신순으로 limit개 조회한다 (화면 하단 표시용)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT report_id, commander_id, who_text, when_text, where_text, "
                f"what_text, how_text, why_text, created_at "
                f"FROM `{_DB}`.`commander_decision` "
                f"ORDER BY created_at DESC, report_id DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        return [dict(row._mapping) for row in rows]
