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
