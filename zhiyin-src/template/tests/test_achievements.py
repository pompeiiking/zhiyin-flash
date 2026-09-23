"""完成记录：由行为日志实时推导，且"什么时候拿到的"必须是那次行为的真实时间。

为什么这一条要单独钉
--------------------
这一屏的全部可信度压在两句话上：**"你做到了"** 与 **"什么时候做到的"**。
两个都只能来自行为日志 —— 一旦这里退化成"打开这一屏的时间"，用户会看到
"今天刚拿到『第一次开口』"，而他其实是三周前做到的。那种错不会报错，
只会让整块记录变得不可信。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from zhiyin_business.services.function import DefaultFunctionService
from zhiyin_kernel.blackboard import BehaviorLog
from zhiyin_kernel.enums import BehaviorEventType
from zhiyin_kernel.registry import BadgeRuleSpec


class _Behaviors:
    """只实现这一屏用到的那一个读法（按发生时间倒序，与仓储契约一致）。"""

    def __init__(self, logs: list[BehaviorLog]) -> None:
        self._logs = logs
        self.calls: list[tuple] = []

    async def recent(self, user_id, *, event_types=None, limit=50):
        self.calls.append((tuple(item.value for item in (event_types or ())), limit))
        rows = [
            item
            for item in self._logs
            if item.user_id == user_id and (not event_types or item.event_type in event_types)
        ]
        return sorted(rows, key=lambda item: item.occurred_at, reverse=True)[:limit]


class _Registry:
    def __init__(self, rules: list[BadgeRuleSpec]) -> None:
        self._rules = rules

    async def list_badge_rules(self) -> list[BadgeRuleSpec]:
        return list(self._rules)


def _log(event: BehaviorEventType, *, days_ago: int, user_id: str = "u1") -> BehaviorLog:
    return BehaviorLog(
        id=f"bhv-{event.value}-{days_ago}",
        user_id=user_id,
        event_type=event,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        payload={},
    )


def _service(behaviors: _Behaviors, rules: list[BadgeRuleSpec]) -> DefaultFunctionService:
    return DefaultFunctionService(
        assets=None,  # type: ignore[arg-type]
        behaviors=behaviors,  # type: ignore[arg-type]
        object_store=None,  # type: ignore[arg-type]
        calendar=None,  # type: ignore[arg-type]
        track_events=None,  # type: ignore[arg-type]
        notifications=None,  # type: ignore[arg-type]
        registry=_Registry(rules),  # type: ignore[arg-type]
    )


def _rules() -> list[BadgeRuleSpec]:
    return [
        BadgeRuleSpec(code="first_answer", trigger_events=["answer"], sort_order=1),
        BadgeRuleSpec(code="first_task_done", trigger_events=["task_done"], sort_order=4),
    ]


@pytest.mark.asyncio
async def test_nothing_done_yet_means_no_badge_and_no_time() -> None:
    service = _service(_Behaviors([]), _rules())
    got = await service.list_achievements("u1")
    assert [item.badge_key for item in got] == ["first_answer", "first_task_done"]
    assert all(not item.unlocked for item in got)
    assert all(item.unlocked_at is None for item in got)


@pytest.mark.asyncio
async def test_unlock_time_is_when_he_actually_did_it_not_when_we_look() -> None:
    """拿到的时刻 = 那条行为**第一次**发生的时间（不是"现在"）。"""
    behaviors = _Behaviors(
        [
            _log(BehaviorEventType.ANSWER, days_ago=21),
            _log(BehaviorEventType.ANSWER, days_ago=3),
            _log(BehaviorEventType.TASK_DONE, days_ago=2),
        ]
    )
    got = {item.badge_key: item for item in await _service(behaviors, _rules()).list_achievements("u1")}

    answer = got["first_answer"]
    assert answer.unlocked and answer.unlocked_at is not None
    # 21 天前那次才是"第一次开口"：写成最近一次、或写成 now，都是假的
    assert (datetime.now(timezone.utc) - answer.unlocked_at).days >= 20

    task = got["first_task_done"]
    assert task.unlocked and task.unlocked_at is not None
    assert (datetime.now(timezone.utc) - task.unlocked_at).days == 2

    # 只读一次：几条规则共用这一份行为（不是每条规则各查一次）
    assert len(behaviors.calls) == 1
    types, limit = behaviors.calls[0]
    assert set(types) == {"answer", "task_done"} and limit == 200


@pytest.mark.asyncio
async def test_a_rule_with_a_typo_does_not_break_the_whole_screen() -> None:
    """规则里写了不存在的事件名：跳过那一项，其余照常 —— 不整屏打不开。"""
    rules = [
        BadgeRuleSpec(code="broken", trigger_events=["没有这个事件"], sort_order=1),
        BadgeRuleSpec(code="first_answer", trigger_events=["answer"], sort_order=2),
    ]
    got = await _service(_Behaviors([_log(BehaviorEventType.ANSWER, days_ago=1)]), rules).list_achievements("u1")
    assert {item.badge_key: item.unlocked for item in got} == {
        "broken": False,
        "first_answer": True,
    }


@pytest.mark.asyncio
async def test_the_view_counts_come_from_the_same_list() -> None:
    """接口那一层只搬形状：拿到几枚、共几枚都由这一份推导结果数出来。"""
    from zhiyin_api.dto.mappers import achievement_list_view

    got = await _service(
        _Behaviors([_log(BehaviorEventType.TASK_DONE, days_ago=1)]), _rules()
    ).list_achievements("u1")
    view = achievement_list_view(got)
    assert (view.unlocked, view.total) == (1, 2)
    assert [item.key for item in view.items] == ["first_answer", "first_task_done"]
