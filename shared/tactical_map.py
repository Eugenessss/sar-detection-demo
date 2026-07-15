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

# 라이트/다크 두 벌. app.py가 st.context.theme.type을 읽어 render_tactical_map(theme=...)
# 로 넘겨주면, JS 쪽에서 CSS 커스텀 프로퍼티(--hq-*)와 베이스 타일(라이트/다크 CARTO)을
# 그때그때 바꿔 그린다 — CCv2의 css/js는 컴포넌트 등록 시점에 한 번만 고정되므로, 색상은
# 여기(Python 상수)가 아니라 data 페이로드를 통해 런타임에 넘겨야 실제로 반영된다.
_THEME_COLORS = {
    "dark": {
        "void": "#0a0e13",
        "panel": "#10161d",
        "accent": "#3ecfc0",
        "border": "#223040",
        "text": "#dbe6ec",
        "faint": "#46586a",
        "base_tile": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    },
    "light": {
        "void": "#eef2f7",
        "panel": "#ffffff",
        "accent": "#2563eb",
        "border": "#dce4ee",
        "text": "#0f172a",
        "faint": "#64748b",
        "base_tile": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    },
}

# 경보 등급별 마커 색은 의미 색상(빨강=긴급 등)이라 테마와 상관없이 고정한다.
_SEVERITY_COLORS = {
    "URGENT": "#ef5354",
    "IMPORTANT": "#f4a340",
    "NOTICE": "#3ecfc0",
}
_FAINT_FALLBACK = "#46586a"

_HTML = """
<div id="hq-map-root">
  <div id="hq-map"></div>
  <div class="hq-frame-corner tl"></div>
  <div class="hq-frame-corner tr"></div>
  <div class="hq-frame-corner bl"></div>
  <div class="hq-frame-corner br"></div>
</div>
"""

# isolate_styles=False로 등록하므로(아래) 이 CSS는 전역에 붙는다 — #hq-map-root로
# 스코프를 좁혀서 다른 페이지 요소에 영향을 안 주게 한다.
# 색은 리터럴이 아니라 CSS 커스텀 프로퍼티(--hq-*)로 두고, paint()가 매 렌더마다
# data.theme에 맞춰 root에 직접 세팅한다 (컴포넌트 등록 시점에 고정되는 css=와 달리
# data는 렌더마다 새로 들어오므로, 테마 전환이 실제로 반영되려면 이 경로여야 한다).
_CSS = """
#hq-map-root {
  position: relative; width: 100%;
  --hq-void: #0a0e13; --hq-panel: #10161d; --hq-accent: #3ecfc0;
  --hq-border: #223040; --hq-text: #dbe6ec; --hq-faint: #46586a;
  --hq-attribution-bg: rgba(10, 14, 19, 0.7);
}
#hq-map { position: relative; width: 100%; height: 100%; background: var(--hq-void); }

#hq-map-root .leaflet-control-zoom a {
  background: var(--hq-panel) !important;
  color: var(--hq-accent) !important;
  border: 1px solid var(--hq-border) !important;
  border-radius: 0 !important;
}
#hq-map-root .leaflet-control-attribution {
  background: var(--hq-attribution-bg) !important;
  color: var(--hq-faint) !important;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px !important;
}
#hq-map-root .leaflet-control-attribution a { color: var(--hq-faint) !important; }

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
  background: var(--hq-panel) !important;
  color: var(--hq-text) !important;
  border: 1px solid var(--hq-accent) !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  padding: 4px 7px !important;
}
#hq-map-root .leaflet-tooltip-top.hq-tooltip::before { border-top-color: var(--hq-accent) !important; }

#hq-map-root .hq-frame-corner {
  position: absolute; width: 20px; height: 20px; z-index: 900; pointer-events: none;
  border: 2px solid var(--hq-accent); opacity: 0.8;
}
#hq-map-root .hq-frame-corner.tl { top: 8px; left: 8px; border-right: none; border-bottom: none; }
#hq-map-root .hq-frame-corner.tr { top: 8px; right: 8px; border-left: none; border-bottom: none; }
#hq-map-root .hq-frame-corner.bl { bottom: 8px; left: 8px; border-right: none; border-top: none; }
#hq-map-root .hq-frame-corner.br { bottom: 8px; right: 8px; border-left: none; border-top: none; }
"""

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

function applyThemeVars(root, colors) {
  if (!colors) return;
  root.style.setProperty("--hq-void", colors.void);
  root.style.setProperty("--hq-panel", colors.panel);
  root.style.setProperty("--hq-accent", colors.accent);
  root.style.setProperty("--hq-border", colors.border);
  root.style.setProperty("--hq-text", colors.text);
  root.style.setProperty("--hq-faint", colors.faint);
  root.style.setProperty(
    "--hq-attribution-bg",
    colors.void.length === 7
      ? "rgba(" + parseInt(colors.void.slice(1, 3), 16) + "," + parseInt(colors.void.slice(3, 5), 16) + "," + parseInt(colors.void.slice(5, 7), 16) + ",0.7)"
      : "rgba(10,14,19,0.7)"
  );
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector("#hq-map-root");
  const mapDiv = parentElement.querySelector("#hq-map");
  if (!root || !mapDiv) return;

  root.style.height = (data.height || 650) + "px";
  mapDiv.style.height = "100%";
  applyThemeVars(root, data.theme_colors);

  function paint() {
    var state = mapDiv.__hqState;
    var themeKey = data.theme_colors && data.theme_colors.base_tile;
    if (state && state.lastTheme !== themeKey) {
      // 라이트/다크 전환: 베이스 타일이 바뀌므로 지도를 통째로 새로 만든다.
      state.map.remove();
      mapDiv.__hqState = null;
      state = null;
    }
    if (!state) {
      var map = L.map(mapDiv, { zoomControl: true, attributionControl: true });
      L.tileLayer(themeKey || "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: "&copy; CARTO"
      }).addTo(map);
      L.tileLayer(data.tile_url, { attribution: "Google Earth Engine" }).addTo(map);
      var layerGroup = L.layerGroup().addTo(map);
      state = { map: map, layerGroup: layerGroup, lastTileUrl: data.tile_url, lastTheme: themeKey };
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
    theme: str = "dark",
) -> Optional[int]:
    """Leaflet 기반 커스텀 지도를 그리고, 이번 실행에서 마커를 클릭했으면 그 alert_id를
    돌려준다 (안 눌렀으면 None).

    alerts: features.HQ_DESK.service.Alert 목록 (latitude/longitude/alert_level/
    sensor_type/asset_name 속성을 읽는다). marker_label은 service.marker_label을
    그대로 넘기면 된다 (등급 -> 한글 라벨 매핑을 그 모듈이 갖고 있으므로 재사용).
    마커 색상(_SEVERITY_COLORS)은 등급별 의미 색이라 테마와 무관하게 고정하지만,
    지도 자체의 배경·패널·테두리·베이스 타일은 theme("dark"/"light")에 따라 JS 쪽에서
    CSS 커스텀 프로퍼티로 매 렌더마다 다시 적용된다 (앱 전역 라이트/다크와 맞추려면
    호출하는 쪽에서 st.context.theme.type을 그대로 넘기면 된다).
    """
    theme_colors = _THEME_COLORS.get(theme, _THEME_COLORS["dark"])

    markers: List[Dict[str, Any]] = []
    for alert in alerts:
        level = alert.alert_level
        markers.append({
            "lat": alert.latitude,
            "lon": alert.longitude,
            "level": level,
            "color": _SEVERITY_COLORS.get(level, _FAINT_FALLBACK),
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
            "theme_colors": theme_colors,
        },
        on_clicked_alert_id_change=lambda: None,
    )
    return getattr(result, "clicked_alert_id", None)
