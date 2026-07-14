"""
[공용 - 커스텀 전술 지도 컴포넌트]
folium(Streamlit 위젯 래퍼)이 아니라, Leaflet.js를 직접 제어하는 완전 커스텀
HTML/CSS/JS 지도. streamlit.components.v1.html()로 iframe에 그린다.

folium 방식과의 차이:
  - 마커·툴팁·줌 버튼 DOM을 우리가 직접 만들고 CSS로 스타일링하므로, Streamlit/folium
    기본 위젯 모양(둥근 모서리·기본 색)이 전혀 안 섞인다. 진짜 발광 펄스(SVG가 아니라
    실제 DOM 엘리먼트라 CSS 애니메이션이 항상 먹는다)도 가능하다.
  - 대신 이 iframe은 Streamlit과 양방향 통신이 안 된다(components.html은 단방향).
    그래서 "마커를 누르면 상세 화면으로 이동" 같은 동작은 이 지도가 아니라 옆의
    기존 st.dataframe 경보 목록에서 그대로 처리한다 — 지도는 순수 시각화용,
    상세 화면 전환은 검증된 기존 방식을 그대로 쓴다.
"""
import json
from typing import Any, Dict, List, Sequence

import streamlit as st

_ACCENT = "#3ecfc0"
_BORDER = "#223040"
_TEXT = "#dbe6ec"
_FAINT = "#46586a"
_PANEL = "#10161d"
_VOID = "#0a0e13"

_SEVERITY_COLORS = {
    "URGENT": "#ef5354",
    "IMPORTANT": "#f4a340",
    "NOTICE": "#3ecfc0",
}

_TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin:0; padding:0; height:100%; background:__VOID__; }
  #map { position:absolute; inset:0; background:__VOID__; }

  .leaflet-control-zoom a {
    background:__PANEL__ !important;
    color:__ACCENT__ !important;
    border:1px solid __BORDER__ !important;
    border-radius:0 !important;
  }
  .leaflet-control-attribution {
    background:rgba(10,14,19,0.7) !important;
    color:__FAINT__ !important;
    font-family:'JetBrains Mono', ui-monospace, monospace;
    font-size:10px !important;
  }
  .leaflet-control-attribution a { color:__FAINT__ !important; }

  .pulse-dot {
    width:12px; height:12px; border-radius:50%;
    border:1.5px solid rgba(255,255,255,0.85);
    position:relative;
  }
  .pulse-dot::after {
    content:"";
    position:absolute; inset:-7px;
    border-radius:50%;
    border:1px solid currentColor;
    opacity:0.6;
    animation: hq-pulse 2.2s ease-out infinite;
  }
  @keyframes hq-pulse {
    0%   { transform:scale(0.5); opacity:0.65; }
    100% { transform:scale(2.1); opacity:0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .pulse-dot::after { animation:none; }
  }

  .hq-tooltip {
    font-family:'JetBrains Mono', ui-monospace, monospace !important;
    font-size:11px !important;
    background:__PANEL__ !important;
    color:__TEXT__ !important;
    border:1px solid __ACCENT__ !important;
    border-radius:0 !important;
    box-shadow:none !important;
    padding:4px 7px !important;
  }
  .leaflet-tooltip-top.hq-tooltip::before { border-top-color:__ACCENT__ !important; }

  .hq-legend {
    position:absolute; top:12px; right:12px; z-index:900;
    background:__PANEL__f5;
    border:1px solid __ACCENT__55;
    padding:10px 12px;
    font-family:'JetBrains Mono', ui-monospace, monospace;
    color:__TEXT__;
    box-shadow:0 6px 20px rgba(0,0,0,0.5);
    backdrop-filter:blur(4px);
    min-width:150px;
  }
  .hq-legend .label {
    font-size:10px; letter-spacing:0.16em; font-weight:700;
    color:__ACCENT__; text-transform:uppercase; margin-bottom:6px;
  }
  .hq-legend .row { display:flex; align-items:center; gap:6px; font-size:11px; margin:3px 0; color:__TEXT__; }
  .hq-legend .sw { width:8px; height:8px; border-radius:50%; display:inline-block; }

  .hq-frame-corner {
    position:absolute; width:20px; height:20px; z-index:900; pointer-events:none;
    border:2px solid __ACCENT__; opacity:0.8;
  }
  .hq-frame-corner.tl { top:8px; left:8px; border-right:none; border-bottom:none; }
  .hq-frame-corner.tr { top:8px; right:8px; border-left:none; border-bottom:none; }
  .hq-frame-corner.bl { bottom:8px; left:8px; border-right:none; border-top:none; }
  .hq-frame-corner.br { bottom:8px; right:8px; border-left:none; border-top:none; }
</style>
</head>
<body>
  <div id="map"></div>
  <div class="hq-frame-corner tl"></div>
  <div class="hq-frame-corner tr"></div>
  <div class="hq-frame-corner bl"></div>
  <div class="hq-frame-corner br"></div>
  <div class="hq-legend">
    <div class="label">Map Legend</div>
    __LEGEND_ROWS__
  </div>
<script>
  var map = L.map('map', { zoomControl: true, attributionControl: true });
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; CARTO'
  }).addTo(map);
  L.tileLayer('__TILE_URL__', { attribution: 'Google Earth Engine' }).addTo(map);
  map.fitBounds(__BOUNDS__);

  var markers = __MARKERS__;
  markers.forEach(function (m) {
    if (m.rings) {
      var steps = [[8000, 0.55], [16000, 0.35], [26000, 0.2]];
      steps.forEach(function (s) {
        L.circle([m.lat, m.lon], {
          radius: s[0], color: m.color, weight: 1, fill: false, opacity: s[1], interactive: false
        }).addTo(map);
      });
    }
    var icon = L.divIcon({
      className: '',
      html: '<div class="pulse-dot" style="background:' + m.color + ';color:' + m.color + ';"></div>',
      iconSize: [12, 12],
      iconAnchor: [6, 6],
    });
    L.marker([m.lat, m.lon], { icon: icon })
      .addTo(map)
      .bindTooltip(m.label, { className: 'hq-tooltip', direction: 'top', offset: [0, -6] });
  });
</script>
</body>
</html>
"""


def render_tactical_map(
    tile_url: str,
    markers: List[Dict[str, Any]],
    bounds: Sequence[Sequence[float]],
    height: int = 650,
) -> None:
    """Leaflet 기반 커스텀 지도를 그린다 (folium을 거치지 않는 완전 커스텀 HTML).

    markers: [{"lat": float, "lon": float, "level": "URGENT"|"IMPORTANT"|"NOTICE",
               "label": str}, ...]. level이 URGENT면 동심원 위협 반경도 같이 그린다.
    bounds: [[남서 lat, lon], [북동 lat, lon]] — folium의 fit_bounds와 같은 형식.
    """
    js_markers = []
    for m in markers:
        color = _SEVERITY_COLORS.get(m.get("level"), _FAINT)
        js_markers.append({
            "lat": m["lat"], "lon": m["lon"], "color": color,
            "label": m.get("label", ""), "rings": m.get("level") == "URGENT",
        })

    legend_rows = "".join(
        f'<div class="row"><span class="sw" style="background:{color};'
        f'box-shadow:0 0 6px {color};"></span>{label}</div>'
        for label, color in [
            ("긴급", _SEVERITY_COLORS["URGENT"]),
            ("중요", _SEVERITY_COLORS["IMPORTANT"]),
            ("특이", _SEVERITY_COLORS["NOTICE"]),
        ]
    )

    html = (
        _TEMPLATE
        .replace("__VOID__", _VOID)
        .replace("__PANEL__", _PANEL)
        .replace("__BORDER__", _BORDER)
        .replace("__ACCENT__", _ACCENT)
        .replace("__TEXT__", _TEXT)
        .replace("__FAINT__", _FAINT)
        .replace("__TILE_URL__", tile_url)
        .replace("__BOUNDS__", json.dumps(list(bounds)))
        .replace("__MARKERS__", json.dumps(js_markers))
        .replace("__LEGEND_ROWS__", legend_rows)
    )
    # st.iframe: src가 URL/파일 패턴이 아니면 원문 HTML로 그대로 그려준다
    # (components.html은 2026-06-01 이후 제거 예정이라 이 방식을 쓴다).
    st.iframe(html, height=height)
