"""手机上的"平台层"：四条浏览器默认行为，删掉不会有任何构建/测试报错。

用户报的是"手机端模块切换跳动、类似卡顿、像闪退"。真机量过之后，
**切换模块本身没有布局位移**（CLS = 0、壳高稳定）—— 那几条"卡/跳/闪"来自
浏览器把网页当网页的那些默认行为。它们的特点是：**在桌面上完全看不见**，
所以删掉一条也没人会发现，只有拿手机用的人会再遇到一次。这就是这个文件存在的理由。

判据全部是"源码里这句话还在"（机械可判），语义写在注释里。
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1]
WEB = TEMPLATE / "zhiyin-web" / "src"
BASE = WEB / "styles" / "base.css"
CONSOLE = WEB / "views" / "ConsoleView.vue"
FLOAT = WEB / "components" / "float" / "FloatLayer.vue"
FLOAT_UI = WEB / "styles" / "ui" / "float.css"


def test_tap_highlight_and_platform_defaults_are_turned_off() -> None:
    """点按高亮、下拉刷新、点击延迟、横屏字放大 —— 四条都要关。

    · `-webkit-tap-highlight-color`：不关，iOS/Android 会给每个可点元素盖一层
      半透明灰（本项目默认值实测是 rgba(0,0,0,.18)）—— 那就是"闪一下"，
      而且它会压掉我们自己设计的按下反馈。
    · `overscroll-behavior: none`：不关，往下拉触发下拉刷新、往上滑整页回弹；
      在一个应用壳里，这两个动作的观感就是"页面自己跳了"。
    · `touch-action: manipulation`：不写，浏览器为判断双击缩放会等 300ms 才派发 click
      —— 按下去到有反应之间那段延迟就是"卡"。
    · `-webkit-text-size-adjust: 100%`：不写，横屏时字被自动放大、整页高度跟着变。
    """
    css = BASE.read_text(encoding="utf-8")
    for needle, why in (
        ("-webkit-tap-highlight-color: transparent", "点按会闪一层灰"),
        ("overscroll-behavior: none", "下拉刷新/整页回弹 = 页面自己跳"),
        ("touch-action: manipulation", "按钮会等 300ms 才有反应"),
        ("-webkit-text-size-adjust: 100%", "横屏时字被放大、高度跟着变"),
    ):
        assert needle in css, f"base.css 少了 `{needle}` —— {why}"


def test_inputs_are_16px_on_phones() -> None:
    """输入框在手机上至少 16px。

    iOS Safari 聚焦到小于 16px 的输入框会**把整个页面放大**且不还原 ——
    在手机上这是最剧烈的一种"跳"，而且只在聚焦时发生，所以看起来像"一切到某个模块就跳"。
    这一条必须能压过组件里更具体的 `.compose input { font-size: … }`（实测 13.5px），
    所以才用了 `!important`：它不是样式选择，是平台阈值。
    """
    css = BASE.read_text(encoding="utf-8")
    assert "font-size: 16px !important" in css, "手机上的输入框字号兜底被删了（iOS 会整页缩放）"
    assert "pointer: coarse" in css or "max-width: 900px" in css, "16px 那条的生效条件没了"


def test_mobile_shell_uses_a_stable_viewport_unit() -> None:
    """窄屏控制台的高度用 `svh` 不用 `dvh`。

    `dvh` 随地址栏收放而变，手机上滚一下页面高度就变一次；而控制台是**多列网格**，
    高度一变整片块重新排版 —— 观感正是"模块切换时跳动"。
    `svh` 是"最矮时的那一屏"，恒定、永不溢出。
    """
    console = CONSOLE.read_text(encoding="utf-8")
    narrow = console[console.index("@media (max-width: 900px), (max-height: 620px)") :][:400]
    assert "min-height: 100svh" in narrow, "窄屏控制台又用回了会变的高度单位"


def test_pinned_floats_use_dvh_not_vh() -> None:
    """贴边浮层用 `dvh`：`vh` 是"地址栏收起后"的高度，首屏会高出一截、底部被盖住。"""
    float_src = FLOAT.read_text(encoding="utf-8")
    assert "calc(100vh" not in float_src, "FloatLayer 又用回了 100vh（手机上底部会被地址栏盖住）"


def test_hover_feedback_is_gated_to_devices_that_can_hover() -> None:
    """会"动"的悬停必须 gate 在真的能悬停的设备上。

    触屏没有 hover，浏览器会替它假装一个：第一次点按套上 `:hover` 并**留在那儿**
    直到点到别处 —— 按钮按完还举着、卡片按完还浮着，用户描述成"按下去不回弹、界面自己在跳"。
    `:active` 不 gate：那是所有输入都该有的按下反馈。

    这一轮只 gate 了"会动的那几处"（base 的按钮抬起、浮片、画像行）。组件里还有一批
    只改颜色的悬停没 gate —— 那些在触屏上表现为"颜色留在按下状态"，观感轻得多，
    但仍然是待办；数量大（实测约 170 条规则），要一并处理得单独一轮 + 先扩守卫。
    """
    base = BASE.read_text(encoding="utf-8")
    assert "@media (hover: hover) and (pointer: fine)" in base, "base.css 里的悬停没有 gate"
    # 会动的三处：base 的按钮抬起、浮片、画像行
    assert base.index("@media (hover: hover) and (pointer: fine)") < base.index(".btn:hover"), (
        "base.css 的 `.btn:hover` 跑到 gate 外面去了"
    )
    float_ui = FLOAT_UI.read_text(encoding="utf-8")
    assert "@media (hover: hover) and (pointer: fine)" in float_ui, (
        "ui/float.css 的抬起没有 gate（触屏点完会一直举着）"
    )
