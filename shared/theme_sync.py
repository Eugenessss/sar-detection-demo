"""
[공용 - 네이티브 테마 감지]
st.context.theme.type은 사용자가 ☰ 메뉴 > Settings > Choose app theme로 테마를
바꿔도 즉시(심지어 다른 위젯을 눌러 rerun이 걸려도) 새 값을 안 돌려주는 경우가
있었다 -- 로그아웃 후 재접속(완전히 새 세션)에서만 반영됨. 그래서 이 값에 기대는
대신, 우리 CSS가 전혀 손대지 않는 네이티브 요소(☰ 메뉴 버튼)의 실제 렌더링된
글자색을 JS로 직접 읽어 라이트/다크를 판정한다 -- 이건 우리 쪽 코드가 아니라
Streamlit 프론트엔드가 테마를 바꾸는 즉시 다시 칠하는 값이라 항상 최신이다.

CCv2 state(setStateValue, 세션 간 유지)로 "dark"/"light" 문자열을 계속 보고하고,
직전 보고값과 달라지면 st.rerun()도 한 번 강제해서 전환이 바로 느껴지게 한다.
"""
from typing import Optional

import streamlit as st

_JS = """
function luminance(el) {
  if (!el) return null;
  var fg = getComputedStyle(el).color;
  var m = fg.match(/\\d+(\\.\\d+)?/g);
  if (!m || m.length < 3) return null;
  var r = +m[0], g = +m[1], b = +m[2];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function detect() {
  // 우리 CSS가 절대 건드리지 않는 네이티브 요소만 후보로 쓴다 -- 우리가 스타일링한
  // 요소를 보면, 아직 안 바뀐 우리 CSS를 보고 "안 바뀜"이라고 판단하는 순환 오류가 난다.
  var el = document.querySelector('[data-testid="stMainMenu"]')
        || document.querySelector('[data-testid="stToolbarActions"]')
        || document.querySelector('[data-testid="stHeader"]');
  var l = luminance(el);
  if (l === null) return null;
  return l > 128 ? "dark" : "light";
}

export default function (component) {
  const { setStateValue } = component;
  var last = null;

  function report() {
    var theme = detect();
    if (theme && theme !== last) {
      last = theme;
      setStateValue("detected_theme", theme);
    }
  }

  report();
  var timer = setInterval(report, 400);

  return function cleanup() {
    clearInterval(timer);
  };
}
"""

_THEME_WATCHER = st.components.v2.component(
    "theme_watcher",
    html="<span></span>",
    js=_JS,
    isolate_styles=False,
)


def detect_ui_theme(default: str = "dark") -> str:
    """네이티브 ☰ 메뉴 요소의 실제 글자색으로 지금 활성 테마를 판정해 돌려준다.

    st.context.theme.type이 못 미더워서(위 모듈 설명 참고) 대신 이 값을 앱 전체
    라이트/다크 판단의 기준으로 쓴다. 컴포넌트가 아직 첫 보고를 안 했으면(최초 로드
    순간) default를 돌려준다. 직전 세션에서 감지한 값과 다르면 그 자리에서 한 번
    rerun해 전환이 바로 반영되게 한다.
    """
    result = _THEME_WATCHER(key="theme_watcher", on_detected_theme_change=lambda: None)
    detected = getattr(result, "detected_theme", None)
    if detected is None:
        return st.session_state.get("_ui_theme_detected", default)

    previous = st.session_state.get("_ui_theme_detected")
    st.session_state["_ui_theme_detected"] = detected
    if previous is not None and previous != detected:
        st.rerun()
    return detected
