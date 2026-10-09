"""`{ immediate: true }` 的 watch 必须写在它要写的东西**之后**。

这类错误今天踩了两次，症状完全一样：**界面报错、功能看起来"点了没反应"**，
而 `vue-tsc` 一声不响（变量确实存在，只是那一刻还没初始化）：

  · `ConsoleView.vue` 的画布上报：回调读 `presentIds` → 依赖 `inStrategy` / `showTimetable`；
  · `PortraitFieldList.vue` 的「点名打开某一条」：回调写 `editingKey`。

原因都一样：`immediate: true` 会让回调在 **setup 阶段**立刻执行，
而 `const` 声明在此之前还没初始化 → `Cannot access '…' before initialization`。

为什么必须守卫：`vite build` 通过、`vue-tsc` 通过、单测全绿，只有**真机**才会看到
那一屏白掉/那一下没反应。它不是风格问题，是"能不能用"的问题。
"""

from __future__ import annotations

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "zhiyin-web" / "src"


def _index_of(source: str, needle: str, where: str) -> int:
    at = source.find(needle)
    assert at >= 0, f"{where} 里找不到 `{needle}` —— 守卫会空跑"
    return at


def test_canvas_truth_report_is_declared_after_its_dependencies() -> None:
    """画布上报那两个集合，必须写在 `inStrategy` / `showTimetable` 之后。"""
    console = (WEB / "views" / "ConsoleView.vue").read_text(encoding="utf-8")
    publish = _index_of(console, "function publishCanvasTruth", "ConsoleView.vue")
    for dep in ("const inStrategy", "const showTimetable"):
        assert _index_of(console, dep, "ConsoleView.vue") < publish, (
            f"画布上报那段在 `{dep}` 之前：真机上会整屏白屏（类型检查看不出来）"
        )


def test_named_edit_request_is_declared_after_the_editing_state() -> None:
    """「点名打开某一条」的 watch，必须写在 `editingKey` 之后。

    它在回调里写 `editingKey`；写在前面 → 一进清单就抛
    "Cannot access 'editingKey' before initialization"，用户点「更正」看起来毫无反应。
    """
    fields = (WEB / "components" / "portrait" / "PortraitFieldList.vue").read_text(encoding="utf-8")
    watch_at = _index_of(fields, "() => props.editKey", "PortraitFieldList.vue")
    state_at = _index_of(fields, "const editingKey", "PortraitFieldList.vue")
    assert state_at < watch_at, (
        "「点名打开某一条」的 watch 挪到了 `editingKey` 之前：真机上会报错且编辑器不开"
    )
