"""对话内"任务做完了/点错了恢复"必须真实改任务状态（不能只回一句话）。

2026-10-18 深度测试：回复"第一项勾掉了"，计划页仍 0/9、任务待执行。
"""

from __future__ import annotations

import pytest

from tests.test_conversation_asset_confirmation import send, setup
from zhiyin_kernel.assets import ActionPhase, ActionPlan, ActionTask


def _plan(*texts: str) -> ActionPlan:
    return ActionPlan(
        id="act_direct",
        plan_id="",
        phases=[
            ActionPhase(
                id="phase_1",
                name="第一周",
                date_range="10月17日—10月23日",
                tasks=[
                    ActionTask(id=f"task_{index}", text=text, done=False)
                    for index, text in enumerate(texts)
                ],
            )
        ],
    )


async def _setup_with_plan(*texts: str):
    c, engine, session = await setup()
    await c.asset_service.save_action_plan(
        "u1", _plan(*texts), depends_on_profile_keys=[], diff_from_previous="测试"
    )
    return c, engine, session


@pytest.mark.asyncio
async def test_ordinal_task_completion_is_really_written() -> None:
    c, engine, session = await _setup_with_plan("整理项目清单", "写简历初稿")
    result = await send(c, session, "第一项我已经做完了")
    assert "已把「整理项目清单」标记为完成" in result.messages[0].text
    plan = await c.asset_service.get_action_plan("u1")
    tasks = [task for phase in plan.phases for task in phase.tasks]
    assert tasks[0].done is True
    assert tasks[1].done is False
    assert engine.requests == [], "能判定时不该再让模型自由发挥（避免假成功语）"


@pytest.mark.asyncio
async def test_undo_restores_the_only_completed_task() -> None:
    c, engine, session = await _setup_with_plan("整理项目清单", "写简历初稿")
    await send(c, session, "第一项已经做完")
    result = await send(c, session, "刚才点错了，恢复成未完成")
    assert "已把「整理项目清单」恢复为未完成" in result.messages[0].text
    plan = await c.asset_service.get_action_plan("u1")
    tasks = [task for phase in plan.phases for task in phase.tasks]
    assert all(task.done is False for task in tasks)


@pytest.mark.asyncio
async def test_named_task_completion_and_already_done_is_idempotent() -> None:
    c, engine, session = await _setup_with_plan("整理项目清单", "写简历初稿")
    await send(c, session, "「写简历初稿」这个任务完成了")
    result = await send(c, session, "「写简历初稿」做完了")
    assert "已经是完成状态" in result.messages[0].text
    plan = await c.asset_service.get_action_plan("u1")
    done = [task for phase in plan.phases for task in phase.tasks if task.done]
    assert [task.text for task in done] == ["写简历初稿"]


@pytest.mark.asyncio
async def test_ambiguous_reference_does_not_guess() -> None:
    c, engine, session = await _setup_with_plan("整理项目清单", "写简历初稿")
    result = await send(c, session, "这一项做完了")
    assert engine.requests, "定位不到唯一任务时应交回模型追问，而不是猜一个"
    plan = await c.asset_service.get_action_plan("u1")
    assert not any(task.done for phase in plan.phases for task in phase.tasks)
