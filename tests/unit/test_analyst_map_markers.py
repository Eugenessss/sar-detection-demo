"""분석관 상황지도의 상태별 DivIcon 마커 생성 테스트."""
import unittest

import folium

from features.ANALYST_DESK import service


class AnalystMapMarkerTest(unittest.TestCase):
    def test_all_status_markers_render_expected_shapes_and_options(self):
        map_obj = folium.Map(location=[40.0, 127.0], zoom_start=7)

        for index, status in enumerate(
            (service.NORMAL_STATUS, "NOTICE", "IMPORTANT", "URGENT")
        ):
            service.add_status_marker(
                map_obj,
                latitude=40.0 + index * 0.1,
                longitude=127.0,
                status=status,
                tooltip=f"[{status}] 테스트",
            )

        html = map_obj.get_root().render()

        for status in ("normal", "notice", "important", "urgent"):
            self.assertIn(f"ops-status-marker--{status}", html)
        self.assertEqual(html.count("@keyframes ops-status-pulse"), 1)
        self.assertIn('"riseOnHover": true', html)
        self.assertIn('"zIndexOffset": 300', html)

    def test_unknown_status_uses_safe_fallback_marker(self):
        map_obj = folium.Map(location=[40.0, 127.0], zoom_start=7)

        service.add_status_marker(
            map_obj,
            latitude=40.0,
            longitude=127.0,
            status="UNEXPECTED",
            tooltip="알 수 없는 상태",
        )

        html = map_obj.get_root().render()
        self.assertIn("ops-status-marker--unknown", html)
        self.assertIn(service.DEFAULT_MARKER_COLOR, html)


if __name__ == "__main__":
    unittest.main()
