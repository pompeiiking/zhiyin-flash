"""复盘给出的调整必须真的落到计划上（实测 ZY-05）。

原本的问题：复盘里说「周六上午删掉，只用周二周四」，行动计划里那三条周六任务
一条都没少 —— 话改了、资产没改，用户第二天看到的还是旧计划，
「改了哪几项」也无从核对。

这里钉住应用器的四条口径：
  1. 关键词能命中（复盘说的是人话，不是 id）；
  2. 已经做完的任务不删 —— 删了"已完成数"会下降，用户看到自己做过的事凭空消失；
  3. 没给 patch、或一条都没命中时**什么都不改**，不造"已调整"的假象；
  4. 挪时间只挪得出得去的那些（能解析的日期），解析不了就保持原样。
"""

from __future__ import annotations

from datetime import datetime

from zhiyin_business.contracts.review import PlanPatch
from zhiyin_business.services.plan_patch import apply_plan_patch
from zhiyin_kernel.assets import ActionPhase, ActionPlan, ActionTask


def _plan() -> ActionPlan:
    return ActionPlan(
        id="plan_1",
        phases=[
            ActionPhase(
                name="本周",
                date_range="10-08 ~ 10-14",
                tag="上线",
                tasks=[
                    ActionTask(id="task_a", text="周六上午把旧网页部署上线"),
                    ActionTask(id="task_b", text="写三行 README"),
                    ActionTask(id="task_c", text="周二晚改一版简历", done=True,
                               done_at=datetime(2026, 10, 9, 20, 0)),
                ],
            )
        ],
    )


def _texts(plan: ActionPlan) -> list[str]:
    return [task.text for phase in plan.phases for task in phase.tasks]


def test_drop_by_keyword_removes_only_that_task() -> None:
    updated, summary = apply_plan_patch(_plan(), PlanPatch(drop_tasks=["周六"]))

    assert _texts(updated) == ["写三行 README", "周二晚改一版简历"]
    assert any("周六" in line for line in summary), "改了哪几项要能说给人听"


def test_drop_by_task_id_works_too() -> None:
    updated, _summary = apply_plan_patch(_plan(), PlanPatch(drop_tasks=["task_b"]))
    assert _texts(updated) == ["周六上午把旧网页部署上线", "周二晚改一版简历"]


def test_completed_task_is_not_dropped() -> None:
    """做过的事不删：删掉会让已完成数下降，用户看到自己的成果消失。"""
    updated, summary = apply_plan_patch(
        _plan(), PlanPatch(drop_tasks=["周二晚改一版简历", "周六"])
    )

    assert "周二晚改一版简历" in _texts(updated)
    assert any("已完成" in line and "保留" in line for line in summary)
    assert "周六上午把旧网页部署上线" not in _texts(updated)


def test_reschedule_task_sets_due_date() -> None:
    updated, summary = apply_plan_patch(
        _plan(), PlanPatch(reschedule_tasks={"task_b": "2026-10-17"})
    )

    task = next(t for p in updated.phases for t in p.tasks if t.id == "task_b")
    assert task.due_date is not None and task.due_date.date().isoformat() == "2026-10-17"
    assert any("2026-10-17" in line for line in summary)


def test_unparsable_date_leaves_task_alone() -> None:
    updated, summary = apply_plan_patch(
        _plan(), PlanPatch(reschedule_tasks={"task_b": "下周四晚上"})
    )
    assert summary == []
    assert updated == _plan()


def test_reschedule_phase_changes_date_range() -> None:
    updated, summary = apply_plan_patch(
        _plan(), PlanPatch(reschedule_phases={"本周": "10-15 ~ 10-21"})
    )
    assert updated.phases[0].date_range == "10-15 ~ 10-21"
    assert any("10-15 ~ 10-21" in line for line in summary)


def test_phase_becomes_empty_is_removed() -> None:
    plan = _plan()
    plan.phases[0].tasks = [ActionTask(id="task_a", text="周六上午把旧网页部署上线")]
    updated, summary = apply_plan_patch(plan, PlanPatch(drop_tasks=["周六"]))
    assert updated.phases == []
    assert any("移除" in line for line in summary)


def test_no_patch_or_no_match_changes_nothing() -> None:
    plan = _plan()
    same, summary = apply_plan_patch(plan, None)
    assert same is plan and summary == []

    untouched, summary2 = apply_plan_patch(plan, PlanPatch(drop_tasks=["周五看展"]))
    assert untouched is plan, "一条都没命中时不能凭空造一次'已调整'"
    assert summary2 == []


async def test_review_conversation_keeps_patch_ids_and_persists_changes() -> None:
    from tests.e2e.test_main_path import _container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_kernel.enums import AssetType
    from zhiyin_orchestration import AgentResult

    class ReviewEngine:
        async def invoke(self, request):
            return AgentResult(
                agent_id=request.agent_id,
                valid=True,
                structured={
                    "conclusion": "先删掉 task_a，把 task_b 挪到下周。",
                    "attribution": "unknown",
                    "minimal_action": {"task_id": "small", "text": "先打开 README"},
                    "guide": {
                        "kind": "task", "text": "先看一眼",
                        "task": {"task_id": "small", "text": "先打开 README"},
                    },
                    "plan_patch": {
                        "drop_tasks": ["task_a"],
                        "reschedule_tasks": {"task_b": "2026-10-17"},
                    },
                },
            )

    container = _container()
    await container.asset_service.save_action_plan("u1", _plan())
    container.orchestrator._agent_engine = ReviewEngine()
    session = await container.orchestrator.enter_task("u1", "stuck")
    result = await container.orchestrator.handle_message(
        TurnRequest(user_id="u1", task_id=session.id, message="我卡住了，改一下计划")
    )
    stored = await container.asset_service.get_action_plan("u1")
    assert [t.id for t in stored.phases[0].tasks] == ["task_b", "task_c"]
    assert stored.phases[0].tasks[0].due_date.date().isoformat() == "2026-10-17"
    assert stored.phases[0].tasks[1].done
    assert "task_a" not in result.messages[0].text
    assert "周六上午把旧网页部署上线" in result.messages[0].text
    assert len(await container.asset_service.list_versions("u1", AssetType.ACTION_PLAN)) == 2
