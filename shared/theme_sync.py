"""
[공용 - 네이티브 테마 전환 감지]
사용자가 ☰ 메뉴 > Settings > Choose app theme로 테마를 바꾸면 프론트엔드는 즉시
다시 칠하지만, 그 시점에 마침 진행 중이던 Python 스크립트 실행이 없으면 서버 쪽
rerun이 곧바로 따라오지 않을 수 있다 -- 그러면 st.context.theme.type이 다음 상호
작용(아무 버튼 클릭 등) 전까지는 계속 예전 값을 들고 있어서, app.py가 고르는
assets/css/app-{light,dark}.css나 지도 색이 실제 화면과 어긋난 채로 멈춰 보인다.

이 모듈은 화면에 안 보이는 CCv2 컴포넌트 하나로, 앱 배경색의 밝기를 400ms마다
확인하다가(= st.context.theme.type이 배경색 밝기로 라이트/다크를 판정하는 것과
같은 신호) 밝기가 명암 기준을 넘어 바뀌면 setTriggerValue로 Python에 알려 즉시
한 번 rerun한다. 그 rerun에서는 이미 프론트엔드가 새 테마를 다 칠한 뒤이므로
st.context.theme.type이 올바른 값을 돌려준다.
"""
import streamlit as st

_JS = """
function luminance() {
  var bg = getComputedStyle(document.body).backgroundColor;
  var m = bg.match(/\\d+(\\.\\d+)?/g);
  if (!m || m.length < 3) return null;
  var r = +m[0], g = +m[1], b = +m[2];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export default function (component) {
  const { setTriggerValue } = component;
  var last = luminance();
  var timer = setInterval(function () {
    var current = luminance();
    if (current === null) return;
    if (last !== null && (current > 128) !== (last > 128)) {
      setTriggerValue("theme_changed", Date.now());
    }
    last = current;
  }, 400);

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


def sync_theme_on_change() -> None:
    """앱 배경 밝기(=테마)가 방금 바뀌었으면 즉시 한 번 rerun해 화면을 새 테마와 맞춘다."""
    result = _THEME_WATCHER(key="theme_watcher", on_theme_changed_change=lambda: None)
    if getattr(result, "theme_changed", None) is not None:
        st.rerun()
