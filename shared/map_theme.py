"""
[공용 - 지도 다크 테마]
folium 지도를 관제 콘솔(C2) 톤에 맞춘다: 어두운 베이스맵 + 리플렛(Leaflet) 컨트롤·
툴팁 재색칠. EE(Earth Engine) 위성영상 레이어 자체는 안 건드리고, 그 아래 베이스맵과
줌 버튼·툴팁 같은 UI 요소만 다크 테마로 바꾼다.

사용법 (build_eo_map() 안에서):
    m = folium.Map(location=..., zoom_start=..., tiles=None)   # tiles=None 필수
    map_theme.add_dark_base(m)                                 # EE 레이어보다 먼저
    ... m.fit_bounds(...), m.add_ee_layer(...) 등 기존 로직 ...
    map_theme.apply_tactical_style(m)                          # 마지막에 한 번
"""
import folium

_ACCENT = "#3ecfc0"
_PANEL = "#10161d"
_PANEL_RAISED = "#182029"
_BORDER = "#223040"
_TEXT = "#dbe6ec"
_FAINT = "#46586a"
_VOID = "#0a0e13"

_LEAFLET_CSS = f"""
<style>
.leaflet-container {{
    background: {_VOID} !important;
}}
.leaflet-control-zoom a {{
    background: {_PANEL} !important;
    color: {_ACCENT} !important;
    border: 1px solid {_BORDER} !important;
}}
.leaflet-control-zoom a:hover {{
    background: {_PANEL_RAISED} !important;
}}
.leaflet-tooltip {{
    background: {_PANEL} !important;
    color: {_TEXT} !important;
    border: 1px solid {_ACCENT} !important;
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    font-size: 11px !important;
    box-shadow: none !important;
}}
.leaflet-tooltip-top:before {{ border-top-color: {_ACCENT} !important; }}
.leaflet-tooltip-bottom:before {{ border-bottom-color: {_ACCENT} !important; }}
.leaflet-control-attribution {{
    background: rgba(10, 14, 19, 0.75) !important;
    color: {_FAINT} !important;
}}
.leaflet-control-attribution a {{ color: {_FAINT} !important; }}
.leaflet-control-layers {{
    background: {_PANEL} !important;
    color: {_TEXT} !important;
    border: 1px solid {_BORDER} !important;
}}
/* 경보 마커(CircleMarker, fill-opacity=0.9)만 은은하게 발광-펄스 — 위협 반경 원
   (Circle, 채움 없음)이나 다른 도형은 이 속성이 없어 영향 안 받는다. */
@keyframes hq-marker-pulse {{
    0%, 100% {{ filter: drop-shadow(0 0 1px currentColor); }}
    50% {{ filter: drop-shadow(0 0 7px currentColor); }}
}}
path.leaflet-interactive[fill-opacity="0.9"] {{
    animation: hq-marker-pulse 2.2s ease-in-out infinite;
}}
@media (prefers-reduced-motion: reduce) {{
    path.leaflet-interactive[fill-opacity="0.9"] {{ animation: none; }}
}}
</style>
"""


def add_dark_base(m: folium.Map) -> None:
    """CartoDB 다크 베이스맵을 맨 아래 레이어로 추가한다.

    folium.Map(..., tiles=None)으로 만든 지도에 EE 위성영상 오버레이보다 먼저
    호출해야 한다 (레이어가 쌓이는 순서 = add_to() 호출 순서).
    """
    folium.TileLayer("CartoDB dark_matter", name="Dark Base", control=False).add_to(m)


def apply_tactical_style(m: folium.Map) -> None:
    """리플렛 컨트롤(줌 버튼·툴팁·저작권 표시)을 다크 콘솔 톤으로 다시 칠한다."""
    m.get_root().header.add_child(folium.Element(_LEAFLET_CSS))
