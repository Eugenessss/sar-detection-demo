"""
[Reports 도메인 - 보고서]
선택한 영상의 정보·탐지 집계·결과 이미지를 받아 분석 보고서(HTML)를 만드는 함수.
화면(view.py)이 직접 호출한다.
결과 이미지는 base64로 <img>에 직접 넣어, 보고서 파일 하나만 있으면 어디서 열어도
이미지가 함께 보이도록 한다 (statistics/report.py와 같은 방식).
"""
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional


def _detections_table_html(detections: List[Dict[str, Any]]) -> str:
    """탐지 집계를 HTML 표로 만든다 (없으면 안내 문구)."""
    if not detections:
        return "<p>(저장된 탐지 결과가 없습니다)</p>"

    rows_html = "".join(
        f"<tr>"
        f"<td>{escape(str(det['class_name']))}</td>"
        f"<td>{escape(str(det['category']))}</td>"
        f"<td class='center'>{escape(str(det['threat_level']))}</td>"
        f"<td class='center'>{escape(str(det['detected_count']))}</td>"
        f"</tr>"
        for det in detections
    )
    return (
        "<table>"
        "<thead><tr><th>장비</th><th>분류</th><th>위협등급</th><th>탐지 수</th></tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def build_analysis_report(
    info: Dict[str, Any],
    detections: List[Dict[str, Any]],
    result_image_b64: Optional[str],
) -> str:
    """영상 정보·탐지 집계·결과 이미지(base64)를 받아 분석 보고서 HTML 문자열을 만든다."""
    image_id = info["image_id"]
    title = f"영상 분석 보고서 #{image_id}"

    image_html = (
        f'<img src="data:image/png;base64,{result_image_b64}" alt="탐지 결과 이미지" style="max-width:100%;">'
        if result_image_b64
        else "<p>(결과 이미지가 없습니다)</p>"
    )

    total_count = sum(int(det["detected_count"]) for det in detections)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
  body {{ font-family: "Malgun Gothic", sans-serif; max-width: 800px; margin: 40px auto; line-height: 1.7; color: #1a1a1a; }}
  .center {{ text-align: center; }}
  h1 {{ font-size: 20px; }}
  h2 {{ font-size: 16px; margin-top: 28px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; font-size: 14px; }}
  th {{ background: #f2f2f2; }}
</style>
</head>
<body>
  <h1 class="center">{escape(title)}</h1>
  <p>1. 작성시각: {escape(f"{datetime.now():%Y-%m-%d %H:%M:%S}")}</p>
  <p>2. 촬영자산: {escape(str(info["asset_name"]))}</p>
  <p>3. 지역명: {escape(str(info["region_name"]))}</p>
  <p>4. 센서: {escape(str(info["sensor_type"]))}</p>
  <p>5. 촬영시각: {escape(str(info["captured_time"]))}</p>
  <p>6. 등록시각: {escape(str(info["created_at"] or "-"))}</p>

  <h2>탐지 결과 (총 {total_count}건)</h2>
  {_detections_table_html(detections)}

  <h2>탐지 결과 이미지</h2>
  {image_html}
</body>
</html>
"""
