"""采集任务不许命中缓存 —— 一次真实的失败换来的守卫。

背景：清空画像之后重新核验学信网，回执照样写着"补上了 8 条"，
而库里一条都没有 —— 因为任务缓存把上一次的结论直接还了回来。
对生成类任务是优化，对采集类任务是**谎报**。
"""

from __future__ import annotations

import pytest

from zhiyin_business.services.ai_tasks import _SIDE_EFFECTING_HEADS


def test_collection_tasks_are_marked_side_effecting() -> None:
    """bind 是采集：它必须每次都真的去取、真的写。"""
    assert "bind" in _SIDE_EFFECTING_HEADS


def test_generation_tasks_stay_cacheable() -> None:
    """生成类任务照旧缓存 —— 不能因为这个修复把缓存全关了。"""
    for head in ("brief", "dim", "gap", "report", "plan", "match"):
        assert head not in _SIDE_EFFECTING_HEADS, head


@pytest.mark.asyncio
async def test_bind_runs_twice_and_never_serves_a_cached_envelope() -> None:
    """连着核验两次，两次都必须真的走到产出逻辑。"""
    from zhiyin_business.contracts.ai_tasks import BindResult
    from zhiyin_business.services.ai_tasks import AiTaskService

    calls: list[str] = []

    class _Chsi:
        async def verify(self, code: str):
            calls.append(code)
            from zhiyin_data_sdk.gateways.chsi import ChsiField, ChsiReport, ChsiReportKind

            return ChsiReport(
                code=code,
                kind=ChsiReportKind.ENROLLMENT,
                fields=[ChsiField(key="school", label="院校名称", value="测试大学")],
            )

    class _Profiles:
        def __init__(self) -> None:
            self.written: list[str] = []

        async def get(self, user_id: str):
            return None

        async def get_fields(self, user_id: str, keys=None):
            return []

        async def update_field(self, user_id, key, value, *, confidence, source, evidence=None):
            self.written.append(key)
            from datetime import datetime, timezone

            from zhiyin_kernel.blackboard import ProfileField
            from zhiyin_kernel.enums import ProfileSource

            return ProfileField(
                key=key,
                value=value,
                confidence=confidence,
                source=ProfileSource(source),
                updated_at=datetime.now(timezone.utc),
            )

    class _Registry:
        """回执上的"谁在替你做这件事"来自注册表，不写死在服务里。"""

        async def get_agent(self, agent_id: str):
            from zhiyin_kernel.registry import AgentDescriptor

            return AgentDescriptor(id=agent_id, name="信息侦查员")

    service = AiTaskService(
        profiles=_Profiles(),  # type: ignore[arg-type]
        behaviors=None,  # type: ignore[arg-type]
        assets=None,  # type: ignore[arg-type]
        chsi=_Chsi(),  # type: ignore[arg-type]
        registry=_Registry(),
    )

    for _ in range(2):
        frames = [frame async for frame in service.stream("u1", "bind.chsi", "123456789012")]
        assert "result" in frames[-1] or "error" in frames[-1]

    assert calls == ["123456789012", "123456789012"], "第二次不该命中缓存"
    assert BindResult is not None


# ---------------------------------------------------------------------------
# 产出作废：事实变了，依据它算出来的那几段不能再用
# ---------------------------------------------------------------------------


def _bare_service(results: object) -> object:
    """只带缓存仓储的服务实例：作废这件事不需要画像 / 行为 / 资产。"""
    from zhiyin_business.services.ai_tasks import AiTaskService

    return AiTaskService(
        profiles=None,  # type: ignore[arg-type]
        behaviors=None,  # type: ignore[arg-type]
        assets=None,  # type: ignore[arg-type]
        results=results,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_event_invalidation_hits_only_the_outputs_that_depend_on_it() -> None:
    """课表变了只清"按课表算的"那几段，别的产出与他人产出都不许动。

    为什么这条重要：作废一次，下次打开就是一次真实模型调用。
    清多了是花钱变慢，清少了是界面上那段话永远停在旧的 —— 两种都得量过才算数。
    """
    from zhiyin_infrastructure.local.repository import InMemoryAiTaskResultRepository

    repo = InMemoryAiTaskResultRepository()
    await repo.put("u1", "brief.today", {"k": "brief"})
    await repo.put("u1", "dim.interest", {"k": "dim"})
    await repo.put("u1", "day.advice.2026-09-25|-480", {"k": "day"})
    await repo.put("u1", "plan.timetable.suggestions", {"k": "timetable"})
    await repo.put("u2", "day.advice.2026-09-25|-480", {"k": "别人的"})

    service = _bare_service(repo)
    removed = await service.invalidate_for_event("u1", "academic_changed")

    # 课表是「这一天怎么用」与「空档课表」的依据，两者的键都清掉
    assert removed == 2
    assert await repo.get("u1", "day.advice.2026-09-25|-480") is None
    assert await repo.get("u1", "plan.timetable.suggestions") is None
    # 与课表无关的两段留着
    assert await repo.get("u1", "brief.today") is not None
    assert await repo.get("u1", "dim.interest") is not None
    # 别人的产出一条都不许动
    assert await repo.get("u2", "day.advice.2026-09-25|-480") is not None


@pytest.mark.asyncio
async def test_an_event_no_output_depends_on_clears_nothing() -> None:
    """没命中任何依据的事件（比如只是聊了一轮）什么都不清。"""
    from zhiyin_infrastructure.local.repository import InMemoryAiTaskResultRepository

    repo = InMemoryAiTaskResultRepository()
    await repo.put("u1", "brief.today", {"k": "brief"})
    await repo.put("u1", "dim.interest", {"k": "dim"})

    service = _bare_service(repo)
    assert await service.invalidate_for_event("u1", "session_changed") == 0
    assert await repo.get("u1", "brief.today") is not None
    assert await repo.get("u1", "dim.interest") is not None


def test_every_cacheable_task_declares_what_it_depends_on() -> None:
    """反向守卫：新加一个 AI 任务，必须在 `_TASK_INPUTS` 里写清它依据什么。

    漏写的症状不会报错，只会"永远不更新"：产出按 key 存在库里，
    事实变了而这份产出没人清，用户就永远看到第一次算出来的那一段。
    所以这条守卫看的是**接口层真实用到的 key**，不是文档。
    """
    import re
    from pathlib import Path

    from zhiyin_api.controllers import ai_controller
    from zhiyin_business.services.ai_tasks import _SIDE_EFFECTING_HEADS, _TASK_INPUTS

    source = Path(ai_controller.__file__).read_text(encoding="utf-8")
    keys = set(re.findall(r'_stream\(\s*request,\s*"([^"]+)"', source))
    assert keys, "没从接口层扫到任何 AI 任务 key —— 守卫本身失效了"

    # 有副作用的任务（学信网核验这种）本来就不进缓存，自然也无从作废
    cacheable = {key for key in keys if key.split(".")[0] not in _SIDE_EFFECTING_HEADS}
    assert cacheable <= set(_TASK_INPUTS), (
        "这些任务的产出没有声明依据，事实变了也不会作废："
        f"{sorted(cacheable - set(_TASK_INPUTS))}"
    )
    # 反过来也一样：表里留着一个已经不存在的任务 key，是没人会读到的死配置
    assert set(_TASK_INPUTS) <= cacheable, (
        f"作废表里有接口层不再产出的 key：{sorted(set(_TASK_INPUTS) - cacheable)}"
    )
