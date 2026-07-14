"""
[공용 - 커스텀 전술 지도 컴포넌트 (CCv2)]
folium/streamlit-folium(v1 위젯 래퍼)이 아니라, Streamlit Custom Components v2
(st.components.v2.component)로 만든 완전 커스텀 지도. Leaflet.js를 우리 JS 코드가
직접 제어하므로 마커·툴팁·범례 DOM을 전부 우리가 그리고 스타일링한다.

v1 (st.iframe/components.v1.html)과의 결정적 차이: CCv2는 iframe을 안 쓰고 진짜
양방향 통신이 된다 — 마커를 클릭하면 setTriggerValue()로 Python에 alert_id를
바로 돌려줄 수 있어서, "마커 클릭 → 상세 화면 전환"이 다시 가능하다.

사용법 (view.py에서):
    clicked_alert_id = render_tactical_map(tile_url, markers, bounds, key="hq_map")
    if clicked_alert_id is not None:
        st.session_state["selected_alert_id"] = clicked_alert_id
        st.session_state["view"] = "detail"
        st.rerun()
"""
from typing import Any, Dict, List, Optional, Sequence

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

_HTML = """
<div id="hq-map-root">
  <div id="hq-map"></div>
  <div class="hq-frame-corner tl"></div>
  <div class="hq-frame-corner tr"></div>
  <div class="hq-frame-corner bl"></div>
  <div class="hq-frame-corner br"></div>
  <div class="hq-legend">
    <div class="hq-legend-label">Map Legend</div>
    <div class="hq-legend-row"><span class="hq-sw" style="background:#ef5354;box-shadow:0 0 6px #ef5354;"></span>긴급 (클릭하면 상세로 이동)</div>
    <div class="hq-legend-row"><span class="hq-sw" style="background:#f4a340;box-shadow:0 0 6px #f4a340;"></span>중요</div>
    <div class="hq-legend-row"><span class="hq-sw" style="background:#3ecfc0;box-shadow:0 0 6px #3ecfc0;"></span>특이</div>
  </div>
</div>
"""

# isolate_styles=False로 등록하므로(아래) 이 CSS는 전역에 붙는다 — #hq-map-root로
# 스코프를 좁혀서 다른 페이지 요소에 영향을 안 주게 한다.
_CSS = """
#hq-map-root { position: relative; width: 100%; }
#hq-map { position: relative; width: 100%; height: 100%; background: __VOID__; }

#hq-map-root .leaflet-control-zoom a {
  background: __PANEL__ !important;
  color: __ACCENT__ !important;
  border: 1px solid __BORDER__ !important;
  border-radius: 0 !important;
}
#hq-map-root .leaflet-control-attribution {
  background: rgba(10, 14, 19, 0.7) !important;
  color: __FAINT__ !important;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px !important;
}
#hq-map-root .leaflet-control-attribution a { color: __FAINT__ !important; }

#hq-map-root .hq-pulse-dot {
  width: 12px; height: 12px; border-radius: 50%;
  border: 1.5px solid rgba(255,255,255,0.85);
  position: relative;
  cursor: pointer;
}
#hq-map-root .hq-pulse-dot::after {
  content: "";
  position: absolute; inset: -7px;
  border-radius: 50%;
  border: 1px solid currentColor;
  opacity: 0.6;
  animation: hq-pulse 2.2s ease-out infinite;
}
@keyframes hq-pulse {
  0%   { transform: scale(0.5); opacity: 0.65; }
  100% { transform: scale(2.1); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  #hq-map-root .hq-pulse-dot::after { animation: none; }
}

#hq-map-root .hq-tooltip {
  font-family: 'JetBrains Mono', ui-monospace, monospace !important;
  font-size: 11px !important;
  background: __PANEL__ !important;
  color: __TEXT__ !important;
  border: 1px solid __ACCENT__ !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  padding: 4px 7px !important;
}
#hq-map-root .leaflet-tooltip-top.hq-tooltip::before { border-top-color: __ACCENT__ !important; }

#hq-map-root .hq-legend {
  position: absolute; top: 12px; right: 12px; z-index: 900;
  background: __PANEL__f5;
  border: 1px solid __ACCENT__55;
  padding: 10px 12px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  color: __TEXT__;
  box-shadow: 0 6px 20px rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  min-width: 170px;
}
#hq-map-root .hq-legend-label {
  font-size: 10px; letter-spacing: 0.16em; font-weight: 700;
  color: __ACCENT__; text-transform: uppercase; margin-bottom: 6px;
}
#hq-map-root .hq-legend-row { display: flex; align-items: center; gap: 6px; font-size: 11px; margin: 3px 0; }
#hq-map-root .hq-sw { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }

#hq-map-root .hq-frame-corner {
  position: absolute; width: 20px; height: 20px; z-index: 900; pointer-events: none;
  border: 2px solid __ACCENT__; opacity: 0.8;
}
#hq-map-root .hq-frame-corner.tl { top: 8px; left: 8px; border-right: none; border-bottom: none; }
#hq-map-root .hq-frame-corner.tr { top: 8px; right: 8px; border-left: none; border-bottom: none; }
#hq-map-root .hq-frame-corner.bl { bottom: 8px; left: 8px; border-right: none; border-top: none; }
#hq-map-root .hq-frame-corner.br { bottom: 8px; right: 8px; border-left: none; border-top: none; }
""".replace("__VOID__", _VOID).replace("__PANEL__", _PANEL).replace("__BORDER__", _BORDER) \
   .replace("__ACCENT__", _ACCENT).replace("__TEXT__", _TEXT).replace("__FAINT__", _FAINT)

_JS = """
function ensureLeaflet(cb) {
  if (window.L) { cb(); return; }
  if (window.__hqLeafletLoading) { window.__hqLeafletCallbacks.push(cb); return; }
  window.__hqLeafletLoading = true;
  window.__hqLeafletCallbacks = [cb];

  var link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
  document.head.appendChild(link);

  var script = document.createElement("script");
  script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  script.onload = function () {
    window.__hqLeafletCallbacks.forEach(function (fn) { fn(); });
    window.__hqLeafletCallbacks = [];
  };
  document.head.appendChild(script);
}

function paintMarkers(map, layerGroup, markers, setTriggerValue) {
  layerGroup.clearLayers();
  markers.forEach(function (m) {
    if (m.rings) {
      [[8000, 0.55], [16000, 0.35], [26000, 0.2]].forEach(function (s) {
        L.circle([m.lat, m.lon], {
          radius: s[0], color: m.color, weight: 1, fill: false, opacity: s[1], interactive: false
        }).addTo(layerGroup);
      });
    }
    var icon = L.divIcon({
      className: "",
      html: '<div class="hq-pulse-dot" style="background:' + m.color + ";color:" + m.color + ';"></div>',
      iconSize: [12, 12],
      iconAnchor: [6, 6],
    });
    var marker = L.marker([m.lat, m.lon], { icon: icon }).addTo(layerGroup);
    marker.bindTooltip(m.label, { className: "hq-tooltip", direction: "top", offset: [0, -6] });
    marker.on("click", function () {
      setTriggerValue("clicked_alert_id", m.alert_id);
    });
  });
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector("#hq-map-root");
  const mapDiv = parentElement.querySelector("#hq-map");
  if (!root || !mapDiv) return;

  root.style.height = (data.height || 650) + "px";
  mapDiv.style.height = "100%";

  function paint() {
    var state = mapDiv.__hqState;
    if (!state) {
      var map = L.map(mapDiv, { zoomControl: true, attributionControl: true });
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: "&copy; CARTO"
      }).addTo(map);
      L.tileLayer(data.tile_url, { attribution: "Google Earth Engine" }).addTo(map);
      var layerGroup = L.layerGroup().addTo(map);
      state = { map: map, layerGroup: layerGroup, lastTileUrl: data.tile_url };
      mapDiv.__hqState = state;
      map.fitBounds(data.bounds);
    } else if (state.lastTileUrl !== data.tile_url) {
      // 센서 필터가 바뀌는 등 타일 자체가 바뀌면 지도를 새로 만든다.
      state.map.remove();
      mapDiv.__hqState = null;
      paint();
      return;
    }
    paintMarkers(state.map, state.layerGroup, data.markers || [], setTriggerValue);
  }

  ensureLeaflet(paint);

  return function cleanup() {
    var state = mapDiv.__hqState;
    if (state) {
      state.map.remove();
      mapDiv.__hqState = null;
    }
  };
}
"""

_TACTICAL_MAP = st.components.v2.component(
    "hq_tactical_map",
    html=_HTML,
    css=_CSS,
    js=_JS,
    isolate_styles=False,
)


def render_tactical_map(
    tile_url: str,
    alerts: List[Any],
    bounds: Sequence[Sequence[float]],
    *,
    marker_label,
    height: int = 650,
    key: str = "hq_tactical_map",
) -> Optional[int]:
    """Leaflet 기반 커스텀 지도를 그리고, 이번 실행에서 마커를 클릭했으면 그 alert_id를
    돌려준다 (안 눌렀으면 None).

    alerts: features.HQ_DESK.service.Alert 목록 (latitude/longitude/alert_level/
    sensor_type/asset_name 속성을 읽는다). marker_label은 service.marker_label을
    그대로 넘기면 된다 (등급 -> 한글 라벨 매핑을 그 모듈이 갖고 있으므로 재사용).
    마커 색상은 이 관제 콘솔 테마 팔레트(_SEVERITY_COLORS)로 고정한다 —
    service.marker_color()는 folium용 색상 이름("red" 등)이라 여기선 안 쓴다.
    """
    markers: List[Dict[str, Any]] = []
    for alert in alerts:
        level = alert.alert_level
        markers.append({
            "lat": alert.latitude,
            "lon": alert.longitude,
            "level": level,
            "color": _SEVERITY_COLORS.get(level, _FAINT),
            "rings": level == "URGENT",
            "label": f"[{marker_label(level)}·{alert.sensor_type}] {alert.asset_name}",
            "alert_id": alert.alert_id,
        })

    result = _TACTICAL_MAP(
        key=key,
        data={
            "tile_url": tile_url,
            "markers": markers,
            "bounds": list(bounds),
            "height": height,
        },
        on_clicked_alert_id_change=lambda: None,
    )
    return getattr(result, "clicked_alert_id", None)
