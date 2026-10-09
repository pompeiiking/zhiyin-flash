"""行动计划与日历节点的 id 必须**稳定**。

实测（ZY-04 / ZY-06）的两条因果链，都由 id 决定：

1. 计划每轮重算，若任务 id 每次都换新的，昨天勾掉的任务今天就是"另一条没做的任务"
   —— 完成状态继承不上，页面永远 0/11；
2. 日历节点若每次都用随机 id 写入，旧节点不会被替换，只会越攒越多
   （实测单账号 57 个节点、其中 24 个标题重复）。

这两条一旦破了不会有异常，只是数字慢慢变得没人信，所以在这里钉住。
"""

from __future__ import annotations

from zhiyin_business.contracts.act import ActOutput
from zhiyin_business.services.asset import DefaultAssetService
from zhiyin_business.services.asset_content import action_plan_from_act

RAW = {
    "conclusion": "先从把旧网页部署上线开始。",
    "phases": [
        {
            "name": "本周",
            "date_range": "10-08 ~ 10-14",
            "tag": "上线",
            "tasks": [{"text": "把旧网页部署上线"}, {"text": "写三行 README"}],
        }
    ],
    "guide": {"kind": "task", "text": "先部署"},
    "reminders": [
        {
            "title": "把旧网页部署上线",
            "due_at": "2026-10-10T10:00:00+00:00",
            "related_task_text": "把旧网页部署上线",
        }
    ],
}


def _plan():
    return action_plan_from_act(ActOutput.model_validate(RAW), user_id="u1")


def test_ids_are_stable_across_regeneration() -> None:
    first, first_nodes = _plan()
    second, second_nodes = _plan()

    ids_first = [task.id for phase in first.phases for task in phase.tasks]
    ids_second = [task.id for phase in second.phases for task in phase.tasks]
    assert ids_first == ids_second, (
        "重排后任务 id 变了 —— 完成状态继承不上（ZY-04），且前端勾选的键也会失效"
    )
    assert all(one.startswith("task_") for one in ids_first), "任务 id 的形态是既有契约"

    assert [node.node_id for node in first_nodes] == [node.node_id for node in second_nodes], (
        "日历节点每次都是新 id —— 旧节点不会被替换，只会越攒越多（ZY-06）"
    )
    assert all(node.node_id.startswith("cal_") for node in first_nodes), "节点 id 的形态是既有契约"


def test_same_text_in_different_phases_does_not_collide() -> None:
    """同一句话出现在两个阶段里，是两条任务 —— 稳定 id 不能把它们并成一条。"""
    raw = {
        "conclusion": "两段都要做同一件事。",
        "phases": [
            {"name": "本周", "date_range": "10-08 ~ 10-14", "tag": "a", "tasks": [{"text": "复盘"}]},
            {"name": "下周", "date_range": "10-15 ~ 10-21", "tag": "b", "tasks": [{"text": "复盘"}]},
        ],
        "guide": {"kind": "task", "text": "各做一次"},
    }
    plan, _nodes = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    ids = [task.id for phase in plan.phases for task in phase.tasks]
    assert len(ids) == 2 and ids[0] != ids[1]

    again, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    assert [task.id for phase in again.phases for task in phase.tasks] == ids


def test_completed_task_survives_a_regenerated_plan() -> None:
    """重算计划不能把"这件事我已经做完了"抹掉（ZY-03 / ZY-04）。"""
    previous, _nodes = _plan()
    done_tasks = [
        previous.phases[0].tasks[0].model_copy(update={"done": True}),
        previous.phases[0].tasks[1],
    ]
    previous = previous.model_copy(
        update={"phases": [previous.phases[0].model_copy(update={"tasks": done_tasks})]}
    )

    regenerated, _ = _plan()  # 模型重新给出的计划：两条都还没勾
    assert [task.done for task in regenerated.phases[0].tasks] == [False, False]

    merged = DefaultAssetService._inherit_task_state(previous, regenerated)
    assert [task.done for task in merged.phases[0].tasks] == [True, False], (
        "重排丢掉了已完成状态 —— 用户明明做完了，页面又回到 0/11"
    )


def test_new_task_stays_open_and_removed_task_is_dropped() -> None:
    """继承只认完成状态，不反过来把用户拉回旧计划。"""
    previous, _nodes = _plan()
    done_tasks = [
        previous.phases[0].tasks[0].model_copy(update={"done": True}),
        previous.phases[0].tasks[1],
    ]
    previous = previous.model_copy(
        update={"phases": [previous.phases[0].model_copy(update={"tasks": done_tasks})]}
    )

    raw = dict(RAW)
    raw["phases"] = [
        {
            "name": "本周",
            "date_range": "10-08 ~ 10-14",
            "tag": "上线",
            # 旧的第一条被拿掉，新增一条"把链接发给同学"
            "tasks": [{"text": "写三行 README"}, {"text": "把链接发给同学"}],
        }
    ]
    regenerated, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    merged = DefaultAssetService._inherit_task_state(previous, regenerated)
    assert [task.text for task in merged.phases[0].tasks] == ["写三行 README", "把链接发给同学"]
    assert [task.done for task in merged.phases[0].tasks] == [False, False], (
        "被删掉的任务不该被继承回来，新任务也应保持未完成"
    )


def test_without_previous_plan_nothing_changes() -> None:
    plan, _nodes = _plan()
    assert DefaultAssetService._inherit_task_state(None, plan) is plan
