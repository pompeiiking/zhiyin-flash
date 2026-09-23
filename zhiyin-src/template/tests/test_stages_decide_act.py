"""③ 决策 / ④ 行动：读得出、选得动、勾得上，而且状态真的落库。

为什么值得单守
--------------
这两个环节此前**只有写没有读**：模型把三套方案与行动计划生成、落库、升版本，
而没有任何接口能把它们读出来，`DirectionPlan.selected` 与 `ActionTask.done`
也没有任何人写。于是这两个环节在用户看来是空的、点不动的两步 ——
而不报错，因为"没有这个接口"不会自己冒出来。

这里钉五件事：

1. 还没走到这一步时，读接口如实返回空（`plans=[]` / `has_plan=False`），不编内容；
2. 选出的一套被标记、其余取消，**可撤回**（再选另一套就是撤回）；
3. 选项不存在时按 1002 抛 ResourceNotFound，而不是静默什么都不做；
4. 勾任务 / 取消勾选都能改状态；
5. 行为日志只记"真的勾掉"（`decision_select` / `task_done`），
   取消勾选**不记** —— 误点不该被当成一条行为信号喂给停滞判定。
"""

from __future__ import annotations


import pytest

from zhiyin_business.contracts.decide import DecideOutput
from zhiyin_business.services.asset_content import (
    action_plan_from_act,
    direction_plans_from_decide,
)
from zhiyin_business.contracts.act import ActOutput
from zhiyin_kernel.enums import BehaviorEventType
from zhiyin_kernel.errors import ResourceNotFound


@pytest.fixture()
def wired():
    from tests.e2e.test_main_path import _container
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)
    return container


async def _seed_plans(container) -> list:
    output = DecideOutput.model_validate(
        {
            "conclusion": "你说想先在设计院做结构，那先把三条路摆开看。",
            "plans": [
                {
                    "option_id": "o1",
                    "role": "main",
                    "name": "结构设计",
                    "target_desc": "设计院结构岗",
                    "match_score": 0.82,
                    "gaps": ["作品集还差一页"],
                    "fit_reason": "结构课连着三个学期都选了它",
                    "main_risk": "作品集没做完",
                },
                {
                    "option_id": "o2",
                    "role": "parallel",
                    "name": "施工技术",
                    "target_desc": "施工单位技术员",
                    "match_score": 0.64,
                    "gaps": [],
                    "fit_reason": "现场经验够用",
                    "main_risk": "与长期方向偏离",
                },
            ],
            # 口径由产出给：它必须能原样读回来，而不是靠前端写一份常量
            "match_score_method": "三叶草契合度 × 可达性（含课程成绩折算）",
            "guide": {"kind": "options", "text": "选一套"},
        }
    )
    plans = direction_plans_from_decide(output, user_id="u1")
    await container.asset_service._assets.save_direction_plans("u1", plans)  # noqa: SLF001
    return plans


@pytest.mark.asyncio
async def test_reads_are_honest_when_nothing_exists(wired) -> None:
    """没走到这一步 → 读接口如实返回空，不编方案也不编计划。"""
    viewer = wired.facade
    plans = await viewer.get_direction_plans("nobody")
    assert plans.plans == [] and plans.selected_id is None

    action = await viewer.get_action_plan("nobody")
    assert action.has_plan is False and action.phases == []


@pytest.mark.asyncio
async def test_select_is_single_choice_and_revocable(wired) -> None:
    """选中是**单选**：一套亮、其余灭；再选另一套就是撤回。"""
    plans = await _seed_plans(wired)
    first, second = plans[0].id, plans[1].id

    view = await wired.facade.select_direction_plan("u1", first)
    assert view.selected_id == first
    assert [p.selected for p in view.plans] == [True, False]

    # 撤回 = 再选另一套
    view = await wired.facade.select_direction_plan("u1", second)
    assert view.selected_id == second
    assert [p.selected for p in view.plans] == [False, True]


@pytest.mark.asyncio
async def test_selecting_a_missing_plan_raises_not_found(wired) -> None:
    """选项不存在 → 1002（ResourceNotFound），不是静默成功。"""
    await _seed_plans(wired)
    with pytest.raises(ResourceNotFound):
        await wired.facade.select_direction_plan("u1", "plan-does-not-exist")


@pytest.mark.asyncio
async def test_task_can_be_ticked_and_unticked(wired) -> None:
    """勾掉能落库，取消勾选也能 —— 点错了要回得去。"""
    plan, _nodes = action_plan_from_act(
        ActOutput.model_validate(
            {
                "conclusion": "你说这周先动作品集，那就从第一页开始。",
                "phases": [
                    {
                        "name": "本周",
                        "date_range": "10-08 ~ 10-14",
                        "tag": "投递",
                        "tasks": [{"text": "做作品集第一页"}, {"text": "写一版简历"}],
                    }
                ],
                "guide": {"kind": "task", "text": "先做第一页"},
            }
        ),
        user_id="u1",
    )
    await wired.asset_service.save_action_plan("u1", plan)

    view = await wired.facade.get_action_plan("u1")
    assert view.has_plan and len(view.phases) == 1
    assert [t.done for t in view.phases[0].tasks] == [False, False]
    assert view.next_task is not None and view.next_task.text == "做作品集第一页"
    # 任务有稳定 id：勾选按它定位，不靠任务文本
    assert all(t.task_id.startswith("task_") for t in view.phases[0].tasks), (
        "行动任务没有稳定 id —— 同一阶段里的同名任务会互相顶掉"
    )

    task_id = view.next_task.task_id
    view = await wired.facade.set_action_task_done("u1", _done(task_id, True))
    assert [t.done for t in view.phases[0].tasks] == [True, False]
    assert view.next_task is not None and view.next_task.text == "写一版简历"

    view = await wired.facade.set_action_task_done("u1", _done(task_id, False))
    assert [t.done for t in view.phases[0].tasks] == [False, False]


@pytest.mark.asyncio
async def test_behavior_log_only_records_real_actions(wired) -> None:
    """只记"真的做了的事"：选方案 → decision_select，勾任务 → task_done；
    取消勾选不记（误点不该喂养"他卡住了"的判断）。
    """
    plans = await _seed_plans(wired)
    plan, _nodes = action_plan_from_act(
        ActOutput.model_validate(
            {
                "conclusion": "你说这周先动作品集，那就从第一页开始。",
                "phases": [
                    {
                        "name": "本周",
                        "date_range": "10-08 ~ 10-14",
                        "tasks": [{"text": "做作品集第一页"}],
                    }
                ],
                "guide": {"kind": "task", "text": "先做第一页"},
            }
        ),
        user_id="u1",
    )
    await wired.asset_service.save_action_plan("u1", plan)
    view = await wired.facade.get_action_plan("u1")
    task_id = view.next_task.task_id

    await wired.facade.select_direction_plan("u1", plans[0].id)
    await wired.facade.set_action_task_done("u1", _done(task_id, True))
    await wired.facade.set_action_task_done("u1", _done(task_id, False))

    logged = await wired.behavior_service.recent("u1")
    kinds = [event.event_type for event in logged]
    assert BehaviorEventType.DECISION_SELECT in kinds
    assert kinds.count(BehaviorEventType.TASK_DONE) == 1
    assert BehaviorEventType.TASK_STALL not in kinds, "取消勾选不该被记成任务停滞"


@pytest.mark.asyncio
async def test_same_named_tasks_do_not_collide(wired) -> None:
    """同一阶段里两条同名任务，勾一条另一条不受影响 —— 这就是 id 存在的意义。"""
    plan, _nodes = action_plan_from_act(
        ActOutput.model_validate(
            {
                "conclusion": "你说先把简历改出来，那就从这一版开始。",
                "phases": [
                    {
                        "name": "本周",
                        "date_range": "10-08 ~ 10-14",
                        "tasks": [{"text": "改简历"}, {"text": "改简历"}],
                    }
                ],
                "guide": {"kind": "task", "text": "先改简历"},
            }
        ),
        user_id="u1",
    )
    await wired.asset_service.save_action_plan("u1", plan)
    view = await wired.facade.get_action_plan("u1")
    ids = [t.task_id for t in view.phases[0].tasks]
    assert len(set(ids)) == 2, "两条同名任务应当拿到两个不同的 id"

    view = await wired.facade.set_action_task_done("u1", _done(ids[0], True))
    assert [t.done for t in view.phases[0].tasks] == [True, False]


def _done(task_id: str, done: bool):
    from zhiyin_api.dto.asset import ActionTaskDoneRequest

    return ActionTaskDoneRequest(task_id=task_id, done=done)


@pytest.mark.asyncio
async def test_match_method_travels_with_the_plans(wired) -> None:
    """匹配口径是**产出的一部分**：生成时那句话要能读回来，不是前端常量。"""
    await _seed_plans(wired)
    view = await wired.facade.get_direction_plans("u1")
    assert view.match_score_method == "三叶草契合度 × 可达性（含课程成绩折算）", (
        "读回来的不是产出里那句口径 —— DecideOutput.match_score_method 在落库时丢了"
    )
