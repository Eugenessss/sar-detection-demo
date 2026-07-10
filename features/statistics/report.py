"""
[Statistics 도메인 - 보고서]
조회 조건(기간·지역)과 분석관이 입력한 담당자명·분석 내용을 받아 통계 보고서(HTML)를 만드는 함수 모음.
화면(view.py)이 직접 호출한다.
st.line_chart는 브라우저(Vega-Lite)에서만 그려지는 그래프라 문서에 그대로 넣을 수 없으므로,
화면에 쓴 것과 같은 시계열 피벗을 matplotlib으로 다시 그려 PNG로 만든 뒤 base64로 <img>에 넣는다.
"""
import base64
import io
from datetime import datetime
from html import escape
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Windows 기본 한글 UI 글꼴. 지정하지 않으면 matplotlib 기본 글꼴로 그려져 한글이 깨진다.
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def _render_chart_image_base64(time_series: pd.DataFrame) -> Optional[str]:
    """시계열 피벗을 꺾은선 그래프 PNG로 그려 base64 문자열로 돌려준다 (그릴 데이터가 없으면 None)."""
    if time_series.empty:
        return None

    fig, ax = plt.subplots(figsize=(7, 3.5))
    time_series.plot(ax=ax)
    ax.set_xlabel("촬영시각")
    ax.set_ylabel("탐지 수")
    ax.legend(title="장비", fontsize=8)
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def build_statistics_report(
    start: datetime,
    end: datetime,
    region_label: str,
    analyst_name: str,
    analysis_text: str,
    time_series: pd.DataFrame,
) -> str:
    """조회 조건·분석 내용을 받아 통계 보고서 HTML 문서를 문자열로 만들어 돌려준다.

    analyst_name/analysis_text는 화면에서 분석관이 직접 입력한 값이라 html.escape로
    이스케이프한 뒤 넣는다 (그대로 넣으면 <script> 등이 실행되는 HTML 삽입 취약점이 된다).
    """
    period_label = f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}"
    title = f"({period_label}) ({region_label}) 통계 보고서"

    chart_b64 = _render_chart_image_base64(time_series)
    chart_html = (
        f'<img src="data:image/png;base64,{chart_b64}" alt="탐지 추이 그래프" style="max-width:100%;">'
        if chart_b64
        else "<p>(그래프로 그릴 데이터가 없습니다)</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
  body {{ font-family: "Malgun Gothic", sans-serif; max-width: 800px; margin: 40px auto; line-height: 1.7; color: #1a1a1a; }}
  .center {{ text-align: center; }}
  h1 {{ font-size: 20px; }}
  .analysis-text {{ white-space: pre-wrap; border: 1px solid #ddd; padding: 12px; margin-top: 8px; }}
  .signature {{ margin-top: 16px; }}
</style>
</head>
<body>
  <h1 class="center">{escape(title)}</h1>
  <p>1. 작성시각: {escape(f"{datetime.now():%Y-%m-%d %H:%M:%S}")}</p>
  <p>2. 조회기간: {escape(period_label)}</p>
  <p>3. 지역명: {escape(region_label)}</p>
  <p>4. 담당분석관: {escape(analyst_name)}</p>
  <p>5. 분석내용:</p>
  {chart_html}
  <div class="analysis-text">{escape(analysis_text or "")}</div>
  <p class="center" style="margin-top: 32px;">위와 같이 보고합니다.</p>
  <p class="center signature">담당 분석관:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(인)</p>
  <p class="center signature">지휘관&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(인)</p>
</body>
</html>
"""