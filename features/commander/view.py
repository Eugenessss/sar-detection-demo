"""
[지휘관 결심 및 명령 화면]
SAR 또는 EO 페이지에서 이미 실행된 분석 결과를 세션에서 받아와, 표적을 요약하고
DB(satellite_intel)의 아군 타격자산(strike_asset)·적군 위치(region)를 가져와 직선거리를
계산한 뒤, 사거리(range_km)를 만족하는 자산만 선택 가능하게 하고, 지휘관이 육하원칙
(누가/언제/어디서/무엇을/어떻게/왜)을 확인·수정해 최종 명령문을 만들도록 돕는 페이지.

읽는 순서(위→아래):
  1) 분석 결과 불러오기 : SAR/EO 세션 결과 확인, 표적 요약 표
  2) 적군 위치·자산 추천 : region 테이블의 적군 좌표, 자산별 거리·사거리 충족 여부, 자산 선택
  3) 육하원칙 작성       : 자동 초안 + 지휘관 수정 폼
  4) 명령문 출력         : 최종 텍스트 확인 및 다운로드
  5) 페이지 진입점

주의: 이 페이지는 SAR/EO의 세션 결과를 '읽기만' 한다. features/sar, features/eo
      폴더의 코드는 참조·수정하지 않는다(프로젝트의 feature 간 비참조 원칙).
"""
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from features.commander import service

_SESSION_DECISION_KEY = "commander_last_decision_text"


# =====================================================================
# 1) 분석 결과 불러오기
# =====================================================================

def render_analysis_summary(
    analysis: service.LatestAnalysis,
    target_summaries: List[service.TargetSummary],
) -> None:
    """세션에서 불러온 분석 결과(출처·파일명)와 표적 요약 표를 보여준다."""
    with st.container(border=True):
        st.subheader("1) 분석 결과")
        info_parts = [f"출처: {analysis.source}", f"파일: {analysis.filename}"]
        if analysis.extra.get("rotate_deg") is not None:
            info_parts.append(f"회전: {analysis.extra['rotate_deg']}도")
        if analysis.extra.get("azimuth") is not None:
            info_parts.append(f"방위각: {analysis.extra['azimuth']}도")
        st.caption(" | ".join(info_parts))

        if not target_summaries:
            st.info("탐지된 표적이 없습니다.")
            return

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "라벨": s.label,
                        "표적 대분류": s.category,
                        "개수": s.count,
                        "최고 신뢰도": s.max_conf,
                    }
                    for s in target_summaries
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


# =====================================================================
# 2) 적군 위치 · 자산 추천/선택 (DB: strike_asset, region)
# =====================================================================

@st.cache_data(ttl=60, show_spinner=False)
def _load_assets_and_enemy(filename: Optional[str]) -> Dict[str, Any]:
    """DB에서 아군 자산·적군 위치를 조회한다 (60초 캐시, 실패해도 화면 유지)."""
    return service.get_assets_and_enemy(filename)


def render_enemy_location_card(db_ctx: Dict[str, Any]) -> None:
    """region 테이블에서 조회한 적군 위치 정보를 보여준다."""
    with st.container(border=True):
        st.subheader("2) 적군 위치")
        if db_ctx["error"]:
            st.warning(f"DB 연결 실패: {db_ctx['error']}")
            return
        if db_ctx["image_id"] is None:
            st.info("파일명이 image_id 형식이 아니어서 적군 위치를 조회할 수 없습니다. (예: 8192.tif)")
            return
        enemy = db_ctx["enemy_location"]
        if enemy is None:
            st.info(f"image_id={db_ctx['image_id']}에 연결된 지역(region) 정보가 없습니다.")
            return
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "region_id": enemy["region_id"],
                        "위도": enemy["latitude"],
                        "경도": enemy["longitude"],
                    }
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_asset_recommendation(ranked_assets: List[Dict[str, Any]]) -> Optional[service.EvaluatedAsset]:
    """자산별 거리·사거리 충족 여부·적합도 점수를 보여주고, 사거리를 만족하는 자산 중에서만
    지휘관이 최종 사용할 자산을 고르게 한다."""
    with st.container(border=True):
        st.subheader("아군 타격자산")

        if not ranked_assets:
            st.warning("등록된 타격자산이 없습니다 (strike_asset 테이블 확인).")
            return None

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "부대": entry["asset"].asset_name,
                        "장비": entry["asset"].name,
                        "종류": entry["asset"].category,
                        "거리(km)": entry["asset"].distance_km,
                        "사거리(km)": entry["asset"].range_km,
                        "사거리 충족": (
                            "충족" if entry["asset"].in_range is True
                            else "사거리 밖" if entry["asset"].in_range is False
                            else "거리 미상"
                        ),
                        "적합도 점수": entry["score"],
                        "일치 표적": ", ".join(entry["matched_labels"]) or "-",
                    }
                    for entry in ranked_assets
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

        # 사거리 밖(in_range=False)으로 확인된 자산은 선택지에서 제외한다.
        # 거리 계산이 안 된 경우(in_range=None)는 판단 불가이므로 선택은 허용하되 안내만 한다.
        selectable = [entry for entry in ranked_assets if entry["asset"].in_range is not False]
        excluded = [entry for entry in ranked_assets if entry["asset"].in_range is False]

        if excluded:
            names = ", ".join(f"{e['asset'].asset_name}({e['asset'].distance_km}km)" for e in excluded)
            st.caption(f"사거리를 벗어나 선택할 수 없는 자산: {names}")

        if not selectable:
            st.error("사거리를 만족하는 타격자산이 없습니다. 자산을 선택할 수 없습니다.")
            return None

        options = {entry["asset"].asset_id: entry["asset"] for entry in selectable}

        def _label(asset_id: int) -> str:
            asset = options[asset_id]
            distance_note = f" · 거리 {asset.distance_km}km" if asset.distance_km is not None else " · 거리 미상"
            return f"{asset.asset_name} ({asset.name}){distance_note}"

        selected_id = st.radio(
            "사용할 타격자산 선택 (사거리를 만족하는 자산만 표시, 적합도 1위가 기본 선택됨)",
            options=list(options.keys()),
            format_func=_label,
            index=0,
            key="commander_selected_asset_id",
        )
        selected_asset = options[selected_id]
        st.caption(selected_asset.notes)
        return selected_asset


# =====================================================================
# 3) 육하원칙 작성
# =====================================================================

def render_5w1h_form(draft: Dict[str, str]) -> Optional[Dict[str, str]]:
    """육하원칙 초안을 보여주고 지휘관이 수정할 수 있는 폼을 그린다.

    '결심 확정' 버튼을 누른 순간의 값을 돌려주고, 그 전에는 None을 돌려준다.
    """
    with st.container(border=True):
        st.subheader("3) 육하원칙 (5W1H) 작성")
        st.caption("자동으로 채운 초안입니다. 실제 상황에 맞게 자유롭게 수정한 뒤 확정하세요.")

        with st.form(key="commander_5w1h_form"):
            who = st.text_input("누가 (Who) - 사용 자산", value=draft["누가"])
            when = st.text_input("언제 (When)", value=draft["언제"])
            where = st.text_area("어디서 (Where)", value=draft["어디서"], height=70)
            what = st.text_area("무엇을 (What) - 표적", value=draft["무엇을"], height=70)
            how = st.text_area("어떻게 (How) - 타격 방법", value=draft["어떻게"], height=70)
            why = st.text_area("왜 (Why) - 판단 근거", value=draft["왜"], height=70)

            submitted = st.form_submit_button("결심 확정", type="primary", use_container_width=True)

        if not submitted:
            return None

        return {
            "누가": who.strip(),
            "언제": when.strip(),
            "어디서": where.strip(),
            "무엇을": what.strip(),
            "어떻게": how.strip(),
            "왜": why.strip(),
        }


# =====================================================================
# 4) 명령문 출력
# =====================================================================

def render_order_output() -> None:
    """세션에 저장된 마지막 확정 명령문을 보여주고 다운로드 버튼을 제공한다."""
    order_text = st.session_state.get(_SESSION_DECISION_KEY)
    if not order_text:
        return

    with st.container(border=True):
        st.subheader("4) 확정된 명령문")
        st.code(order_text, language="text")
        st.download_button(
            "명령문 텍스트 다운로드 (.txt)",
            data=order_text,
            file_name="commander_order.txt",
            mime="text/plain",
            use_container_width=True,
        )


# =====================================================================
# 5) 페이지 진입점
# =====================================================================

def render_commander_page() -> None:
    """지휘관 결심 및 명령 페이지 전체를 그린다."""
    st.title("지휘관 결심 및 명령")
    st.caption("SAR/EO 분석 결과와 DB의 아군 자산·적군 위치를 바탕으로 타격자산 선택과 육하원칙 작성을 보조합니다.")

    analysis = service.get_latest_analysis()
    if analysis is None:
        st.info(
            "먼저 SAR 또는 EO 페이지에서 이미지를 분석(실행)하세요. "
            "이 페이지는 그 페이지들이 마지막으로 실행한 결과를 그대로 가져옵니다."
        )
        return

    target_summaries = service.summarize_targets(analysis.detections)
    render_analysis_summary(analysis, target_summaries)

    db_ctx = _load_assets_and_enemy(analysis.filename)
    render_enemy_location_card(db_ctx)

    if db_ctx["error"]:
        st.warning(f"타격자산 조회 실패: {db_ctx['error']}")
        return

    ranked_assets = service.recommend_assets(target_summaries, db_ctx["assets"])
    selected_asset = render_asset_recommendation(ranked_assets)
    if selected_asset is None:
        return

    draft = service.build_5w1h_draft(analysis, target_summaries, selected_asset)
    confirmed = render_5w1h_form(draft)

    if confirmed is not None:
        order_text = service.format_order_text(confirmed)
        st.session_state[_SESSION_DECISION_KEY] = order_text
        st.success("결심이 확정되었습니다. 아래에서 명령문을 확인하세요.")

    render_order_output()
