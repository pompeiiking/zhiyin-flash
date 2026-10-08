"""待办块必须展示真的待办 —— 判据不能再是"这一阶段的评价"（issue #21）。

症状：**有待办数据时**主界面仍写着"今天这一件还没定下来"。
机制很具体：这一块的判据只有 `session.wsPanels.action`（工作台对**这一阶段**的评价），
而后端 degraded（或还没走到 ④）时它恒为空串 —— 于是卡片必现空态；
真正的待办（`actionPlan.phases[].tasks`、`customTodos`）一条都没进渲染。

同一条陈旧判据还留在画布的块权重里（`isEmptyBlock`），会把**有待办的块**当成空块，
分到更小的格位、更容易掉进紧凑形态 —— 内容修好了、块还是被当空的。
两处必须同源，所以这里一起钉。
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1]
WEB = TEMPLATE / "zhiyin-web" / "src"
TODO = WEB / "components" / "console" / "TodoBubble.vue"
TASKS = WEB / "components" / "console" / "TasksOverlay.vue"
SESSION = WEB / "stores" / "session.ts"
CONSOLE = WEB / "views" / "ConsoleView.vue"


def test_todo_bubble_renders_both_sources() -> None:
    """两个来源都要读、都要摊成同一个形状才可能渲染出来。"""
    source = TODO.read_text(encoding="utf-8")
    assert "session.actionPlan" in source, "待办块必须读行动计划里的任务"
    assert "customTodos" in source, "待办块必须读自建待办"
    assert "planLines" in source and "todoLines" in source, "两个来源先摊平再渲染"


def test_empty_state_predicate_has_no_stage_evaluation() -> None:
    """整块的渲染条件必须是"有没有待办"（`head`），不能是阶段评价。

    注意分寸：那句评价**可以**挂在 `v-if="liveAction"` 上 —— 它现在只是标题下面
    一条来源说明，有就写、没有就不写。要钉的是"别拿它当整块的开关"。
    """
    source = TODO.read_text(encoding="utf-8")
    assert 'v-if="head" class="now"' in source, "「现在/最后一件」应由待办本身决定"
    assert '<div v-if="liveAction" class="now">' not in source, (
        "整块的渲染条件不能挂回阶段评价上 —— 那就是这条 bug 的机制"
    )
    assert 'v-if="!liveAction"' not in source, "NextAsk 的显示条件同样不能挂在它上面"


def test_canvas_weight_and_the_card_share_one_predicate() -> None:
    """画布的块权重必须和卡片用同一个判据（store 的 `hasTodos`）。"""
    console = CONSOLE.read_text(encoding="utf-8")
    assert "if (id === 'todo') return !session.wsPanels?.action" not in console, (
        "块权重里还留着旧判据：有待办的块会被当成空块"
    )
    assert "if (id === 'todo') return !session.hasTodos" in console
    store = SESSION.read_text(encoding="utf-8")
    assert "hasTodos(state): boolean" in store, "store 里要有 hasTodos（与卡片同源）"


def test_all_tasks_reachable_from_the_card() -> None:
    """卡片上的「全部任务 →」要真的能看到那些任务，包括计划排的。"""
    source = TASKS.read_text(encoding="utf-8")
    assert "planRows" in source, "「全部任务」里必须列行动计划排的任务（否则点进去是空清单）"
    assert "去行动计划里勾" in source, "计划任务的勾选只能回行动计划那一处改（不复制第二份写逻辑）"
