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
조인해서, 같은 지역(region_id)에서 촬영된 최근 사진들 중 result_image_path가 채워진
것만 최신 3장(H-4/H-2/H-Hour) 골라 온다. 혹시 DB에 아직 연결이 안 되어 있으면
(구버전 seed 데이터 등) 프로젝트 루트 result_image/ 폴더를 훑는 방식으로 대신한다.
파일명 끝의 HHMMSS(예: 100000 -> 10:00:00)를 촬영 시각 라벨로 쓴다.

지도(EO 위성 배경) 생성 로직은 view.py·detail_view.py가 똑같이 쓰므로 build_eo_map()
하나로 공용화했다. 아군 자산(아군 타격 자산)은 ally_asset 테이블(부대+장비+무장 조합별
사거리·타격반경)에서 조회하고, 적군 위치(alert에 이미 조인된 region 좌표)까지의
직선거리를 하버사인 공식으로 계산해 사거리 충족 여부를 판정한다.
"""
import re
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional

import ee
import folium
from sqlalchemy import text

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

# 지도에는 전체 경보 이력이 아니라, 가장 최근에 생성된 경보 1건만 표시한다.
# (예: alert 테이블에 행이 16개 있어도 그중 가장 최신 1개만 가져온다.)
MAX_ALERTS_ON_MAP = 1

# 프로젝트 루트 (result_image_path 같은 DB의 상대경로를 실제 파일로 바꿀 때 기준 폴더).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# DB 연결이 안 된 구버전 alert를 위한 대체용 폴더 스캔 (프로젝트 루트 바로 아래 result_image/).
IMAGE_ROOT_DIR = PROJECT_ROOT / "result_image"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
MAX_IMAGES_PER_ALERT = 3

# 파일명 끝의 "HHMMSS.확장자" 부분에서 시각을 뽑아내는 정규식.
# 예: "425-1_개풍군_1_EO_2023-12-30 100000.png" -> "100000" (10:00:00)
_TIME_SUFFIX_RE = re.compile(r"(\d{6})\.\w+$")


def _image_time_key(path: Path) -> str:
    """정렬용 키: 파일명 끝의 HHMMSS. 못 찾으면 파일명 그대로를 키로 쓴다."""
    match = _TIME_SUFFIX_RE.search(path.name)
    return match.group(1) if match else path.name


def image_time_label(path: Path) -> str:
    """파일명 끝의 HHMMSS를 'HH:MM' 표시용 라벨로 바꾼다 (못 찾으면 파일명)."""
    match = _TIME_SUFFIX_RE.search(path.name)
    if not match:
        return path.stem
    hhmmss = match.group(1)
    return f"{hhmmss[0:2]}:{hhmmss[2:4]}"

# alert -> change_event -> image_analysis -> region / equipment 순서로 조인해
# 지도에 필요한 값을 한 번에 가져온다. region_id가 없는 image는 자동으로 제외된다.
_ALERT_QUERY = f"""
    SELECT
        a.alert_id, a.alert_level, a.title, a.message,
        eq.class_name, eq.category AS eq_category, eq.threat_level, eq.description AS eq_description,
        r.region_name, r.latitude, r.longitude
    FROM `{_DB}`.`alert` a
    JOIN `{_DB}`.`change_event` ce ON a.change_id = ce.change_id
    JOIN `{_DB}`.`image_analysis` ia ON ce.current_image_id = ia.image_id
    JOIN `{_DB}`.`region` r ON ia.region_id = r.region_id
    JOIN `{_DB}`.`equipment` eq ON ce.equipment_id = eq.equipment_id
"""


@dataclass
class Alert:
    """alert_id 세션 하나를 담은 것 (위치정보·적군자산·경보수준·제목 등)."""
    alert_id: int
    latitude: float
    longitude: float
    alert_level: str       # DB enum 원본값 (URGENT/IMPORTANT/NOTICE)
    asset_name: str = ""   # 적군자산(장비) 이름 (equipment.class_name)
    asset_category: str = ""       # 적군자산 종류 (equipment.category)
    asset_threat_level: Optional[int] = None  # 적군자산 위협도 (equipment.threat_level)
    asset_description: str = ""    # 적군자산 설명 (equipment.description)
    title: str = ""        # 경보제목
    summary: str = ""      # 변화요약(경보 발생 근거)
    region: str = ""       # 지역


def _row_to_alert(row) -> Alert:
    m = dict(row._mapping)
    return Alert(
        alert_id=m["alert_id"],
        latitude=float(m["latitude"]),
        longitude=float(m["longitude"]),
        alert_level=m["alert_level"],
        asset_name=m["class_name"] or "",
        asset_category=m["eq_category"] or "",
        asset_threat_level=m["threat_level"],
        asset_description=m["eq_description"] or "",
        title=m["title"] or "",
        summary=m["message"] or "",
        region=m["region_name"] or "",
    )


def get_alerts(limit: int = MAX_ALERTS_ON_MAP) -> List[Alert]:
    """지도에 표시할 경보 목록을 DB에서 최신순으로 limit개만 조회한다."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(_ALERT_QUERY + " ORDER BY a.created_at DESC LIMIT :limit"),
            {"limit": limit},
        )
        return [_row_to_alert(row) for row in rows]


def get_alert_by_id(alert_id: int) -> Optional[Alert]:
    """alert_id 하나에 해당하는 경보를 DB에서 조회한다 (없으면 None)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(_ALERT_QUERY + " WHERE a.alert_id = :alert_id"),
            {"alert_id": alert_id},
        ).fetchone()
    return _row_to_alert(row) if row else None


# alert -> change_event -> (current_image의) region_id로, 같은 지역에서 촬영된
# 사진들 중 result_image_path가 채워진 것만, current_image 시각 이전(포함)으로 최신
# 3장을 가져온다. 2시간 간격 촬영이므로 이 3장이 각각 H-4/H-2/H-Hour에 해당한다.
_ALERT_IMAGES_QUERY = f"""
    SELECT ia2.result_image_path, ia2.original_image_path, ia2.captured_time
    FROM `{_DB}`.`alert` a
    JOIN `{_DB}`.`change_event` ce ON a.change_id = ce.change_id
    JOIN `{_DB}`.`image_analysis` ia ON ce.current_image_id = ia.image_id
    JOIN `{_DB}`.`image_analysis` ia2 ON ia2.region_id = ia.region_id
    WHERE a.alert_id = :alert_id
      AND ia2.captured_time <= ia.captured_time
      AND ia2.result_image_path IS NOT NULL
      AND ia2.result_image_path <> ''
    ORDER BY ia2.captured_time DESC
    LIMIT {MAX_IMAGES_PER_ALERT}
"""


def _scan_image_root_dir() -> List[Path]:
    """(대체용) result_image/ 폴더를 훑어 파일명 끝 HHMMSS 순으로 최대 3장 찾는다."""
    if not IMAGE_ROOT_DIR.is_dir():
        return []
    images = sorted(
        (p for p in IMAGE_ROOT_DIR.iterdir()
         if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS),
        key=_image_time_key,
    )
    return images[:MAX_IMAGES_PER_ALERT]


def get_alert_images(alert_id: int) -> List[Path]:
    """alert -> change_event -> image_analysis로 조인해 result_image_path를 가져온다.

    DB에서 못 찾으면(과거 seed 데이터처럼 change_event가 아직 실제 사진에 연결
    안 된 경우) result_image/ 폴더를 훑는 방식으로 대신한다.
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
        if not rel_path:
            continue
        full_path = PROJECT_ROOT / rel_path
        if full_path.is_file():
            images.append(full_path)

    return images[:MAX_IMAGES_PER_ALERT] if images else _scan_image_root_dir()


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
