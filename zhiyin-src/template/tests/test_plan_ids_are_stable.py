"""行动计划与日历节点的 id 必须**稳定**。

实测（ZY-04 / ZY-06）的两条因果链，都由 id 决定：

1. 计划每轮重算，若任务 id 每次都换新的，昨天勾掉的任务今天就是"另一条没做的任务"
   —— 完成状态继承不上，页面永远 0/11；
2. 日历节点若每次都用随机 id 写入，旧节点不会被替换，只会越攒越多
   （实测单账号 57 个节点、其中 24 个标题重复）。

这两条一旦破了不会有异常，只是数字慢慢变得没人信，所以在这里钉住。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

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


@pytest.mark.parametrize("change", ["reverse", "insert", "remove"])
def test_other_tasks_do_not_change_a_task_identity(change: str) -> None:
    previous, _ = _plan()
    original = previous.phases[0].tasks[1]
    raw = deepcopy(RAW)
    tasks = raw["phases"][0]["tasks"]
    if change == "reverse":
        tasks.reverse()
    elif change == "insert":
        tasks.insert(0, {"text": "先整理项目文件"})
    else:
        tasks.pop(0)
    regenerated, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    same = next(t for t in regenerated.phases[0].tasks if t.text == original.text)
    assert same.id == original.id


@pytest.mark.parametrize("legacy_id", ["task_old_random", ""])
def test_completed_legacy_task_survives_reordering(legacy_id: str) -> None:
    previous, _ = _plan()
    completed = previous.phases[0].tasks[1]
    completed.id = legacy_id
    completed.done = True
    completed.done_at = datetime(2026, 10, 9, tzinfo=timezone.utc)
    raw = deepcopy(RAW)
    raw["phases"][0]["tasks"].reverse()
    regenerated, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    merged = DefaultAssetService._inherit_task_state(previous, regenerated)
    same = merged.phases[0].tasks[0]
    assert same.done and same.done_at == completed.done_at
    if legacy_id:
        assert same.id == legacy_id


def test_duplicate_tasks_stay_distinct_after_an_unrelated_insertion() -> None:
    raw = deepcopy(RAW)
    raw["phases"][0]["tasks"] = [{"text": "复盘"}, {"text": "复盘"}]
    previous, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    ids = [t.id for t in previous.phases[0].tasks]
    assert len(set(ids)) == 2
    previous.phases[0].tasks[1].done = True
    raw["phases"][0]["tasks"].insert(0, {"text": "整理项目"})
    regenerated, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    merged = DefaultAssetService._inherit_task_state(previous, regenerated)
    assert [t.id for t in merged.phases[0].tasks[1:]] == ids
    assert [t.done for t in merged.phases[0].tasks] == [False, False, True]


def test_ambiguous_legacy_duplicates_are_not_guessed() -> None:
    raw = deepcopy(RAW)
    raw["phases"][0]["tasks"] = [
        {"id": "old_a", "text": "复盘", "done": True},
        {"id": "old_b", "text": "复盘"},
    ]
    previous, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    raw["phases"][0]["tasks"] = [{"text": "复盘"}, {"text": "复盘"}]
    regenerated, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    merged = DefaultAssetService._inherit_task_state(previous, regenerated)
    assert [t.done for t in merged.phases[0].tasks] == [False, False]


async def test_identical_regeneration_reuses_version_and_completed_state() -> None:
    from tests.e2e.test_main_path import _container
    from zhiyin_kernel.enums import AssetType

    container = _container()
    first, _ = _plan()
    initial = await container.asset_service.save_action_plan("u1", first)
    await container.asset_service.mark_action_task_done("u1", first.phases[0].tasks[1].id)
    completed = await container.asset_service.get_action_plan("u1")
    regenerated, _ = _plan()
    repeated = await container.asset_service.save_action_plan("u1", regenerated)
    assert repeated.id == initial.id and repeated.version == 1
    stored = await container.asset_service.get_action_plan("u1")
    assert stored == completed
    assert len(await container.asset_service.list_versions("u1", AssetType.ACTION_PLAN)) == 1

    raw = deepcopy(RAW)
    raw["phases"][0]["date_range"] = "10-15 ~ 10-21"
    changed, _ = action_plan_from_act(ActOutput.model_validate(raw), user_id="u1")
    version = await container.asset_service.save_action_plan("u1", changed)
    stored = await container.asset_service.get_action_plan("u1")
    assert version.version == 2
    assert stored.id == first.id
    assert stored.phases[0].date_range == "10-15 ~ 10-21"
    assert stored.phases[0].tasks[1].done
