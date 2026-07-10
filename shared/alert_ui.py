"""
[공용 - 경보 결과 표시]
DB 저장 뒤 실행한 변화 분석 결과(ChangeAnalysisOutcome)를 화면에 알려주는 공용 UI.
SAR/EO 탐지 화면이 똑같이 쓰던 함수라 shared로 올렸다 (두 화면의 복사본을 대체).
등급별 색상 메시지 + 토스트로 표시한다.
"""
import streamlit as st

from shared.change_analysis import ChangeAnalysisOutcome


def render_change_analysis_result(outcome: ChangeAnalysisOutcome) -> None:
    """DB 저장 뒤 실행한 변화 분석 결과를 사용자에게 알려준다."""
    if outcome.previous_image_id is None:
        message = "[최초 영상] 비교 기준 영상이 등록되었습니다."
        st.info(f"{message} change_event에는 기록하지 않았습니다.")
        st.toast(message)
        return

    if outcome.events_created == 0 and not outcome.alerts_created:
        if outcome.unchanged_supported:
            st.info("이전 영상과 수량이 같아 새 분석 로그를 만들지 않았습니다.")
        else:
            st.info("변화 없음. 현재 DB event_type enum에 UNCHANGED가 없어 change_event에는 저장하지 않았습니다.")
        return

    st.success(
        f"변화 분석 완료: change_event {outcome.events_created}건, "
        f"alert {len(outcome.alerts_created)}건 생성"
    )
    for alert in outcome.alerts_created:
        message = f"[{alert['alert_level']}] {alert['title']}"
        if alert["alert_level"] == "URGENT":
            st.error(message)
        elif alert["alert_level"] == "IMPORTANT":
            st.warning(message)
        else:
            st.info(message)
        st.toast(message)
