"""
[공용 - 네이티브 테마 전환 시 자동 새로고침]
확인해보니 ☰ 메뉴 > Settings에서 테마(Light/Dark/System)를 눌러도 지금 세션에서는
그 어떤 것도(우리 CSS는 물론 st.dataframe 같은 네이티브 위젯까지) 곧바로 안 바뀌고,
실제로 페이지를 새로고침(또는 로그아웃 후 재접속 = 새 세션)해야만 전체가 새
테마로 반영된다 -- st.context.theme.type도 그 전까지는 계속 예전 값을 돌려준다.

그래서 "감지해서 rerun"이 아니라, 테마 라디오 버튼(data-testid가
"stMainMenuItem-theme-"로 시작하는 메뉴 항목 -- Light/Dark/System)을 클릭하는
순간을 직접 잡아 자동으로 window.location.reload()를 걸어 로그아웃 후 재접속과
같은 효과를 낸다. document 전체에 리스너를 한 번만(중복 방지 플래그) 붙여두고,
컴포넌트가 rerun마다 다시 마운트돼도 다시 붙이지 않는다.
"""
import streamlit as st

_JS = """
export default function (component) {
  if (window.__hqThemeReloadHooked) return;
  window.__hqThemeReloadHooked = true;
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest('[data-testid^="stMainMenuItem-theme-"]');
    if (el) {
      setTimeout(function () { window.location.reload(); }, 200);
    }
  }, true);
}
"""

_THEME_RELOAD_HOOK = st.components.v2.component(
    "theme_reload_hook",
    html="<span></span>",
    js=_JS,
    isolate_styles=False,
)


def install_theme_reload_hook() -> None:
    """Settings 메뉴의 테마 라디오를 클릭하면 자동으로 페이지를 새로고침한다."""
    _THEME_RELOAD_HOOK(key="theme_reload_hook")
