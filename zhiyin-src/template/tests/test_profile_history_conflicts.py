"""画像历史版本与冲突并存（《个人画像设计-2026-10-20》第 4、7 节）。

锁住三件事：
1. 当前值仍是一行一键的兼容投影（旧 API 不改）；
2. 每次值被替代时旧值进历史，不丢；
3. 自动记忆遇到与当前值不一致的新说法时**不覆盖**，而是并存为冲突提案，
   由用户裁定「以新说法为准」还是「保留当前记录」。
"""

from __future__ import annotations

import pytest

from tests.e2e.test_main_path import _container
from zhiyin_business.services.dialogue_runtime import active_dialogue
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_kernel.enums import ProfileEntryStatus
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_orchestration import AgentResult


class _Model:
    def __init__(self, callback=None) -> None:
        self.callback = callback
        self.text = "记下了。"

    async def invoke(self, request):
        if self.callback:
            await self.callback(active_dialogue.get())
        return AgentResult(agent_id=request.agent_id, raw_text=self.text, valid=True)


async def _container_with_model(callback=None):
    container = _container()
    from zhiyin_business.services.dynamic_config import load_snapshot

    await load_snapshot(container.registry_service)
    container.orchestrator._agent_engine = _Model(callback)
    session = await container.orchestrator.enter_task("u1", "free_chat")
    return container, session


async def _send(container, session, text="继续"):
    return await container.orchestrator.handle_message(
        TurnRequest(user_id="u1", task_id=session.id, message=text)
    )


def _action(payload: dict, *, evidence: str, authorization: str = "automatic") -> dict:
    return {
        "operation": "profile.update",
        "payload": {**payload, "assertion_type": "affirmative_self_statement"},
        "authorization": authorization,
        "evidence": evidence,
    }


@pytest.mark.asyncio
async def test_old_value_goes_to_history_and_current_projection_stays_single_row() -> None:
    container, _ = await _container_with_model()
    await container.profile_service.update_field(
        "u1", "major", "数学", confidence=0.9, source="conversation"
    )
    await container.profile_service.correct_field("u1", "major", "人工智能")
    current = await container.profile_service.get_fields("u1", ["major"])
    assert [field.value for field in current] == ["人工智能"]
    history = await container.profile_service.list_revisions("u1", "major")
    assert [item.value for item in history] == ["数学"]
    assert history[0].status is ProfileEntryStatus.SUPERSEDED
    assert history[0].change_reason


@pytest.mark.asyncio
async def test_automatic_conflicting_statement_is_stored_side_by_side_not_overwritten() -> None:
    async def save(runtime) -> None:
        await runtime.action(_action({"key": "major", "value": "人工智能"}, evidence="人工智能"))

    container, session = await _container_with_model(save)
    await container.profile_service.update_field(
        "u1", "major", "数学", confidence=0.9, source="conversation"
    )
    await _send(container, session, "人工智能")
    current = next(f for f in await container.profile_service.get_fields("u1") if f.key == "major")
    assert current.value == "数学"
    conflicts = await container.profile_service.list_conflicts("u1")
    assert [item.value for item in conflicts] == ["人工智能"]
    assert conflicts[0].status is ProfileEntryStatus.CONFLICT
    profile = await container.profile_service.get("u1")
    assert [item.value for item in profile.conflicts] == ["人工智能"]


@pytest.mark.asyncio
async def test_resolving_with_the_new_statement_updates_the_projection() -> None:
    async def save(runtime) -> None:
        await runtime.action(_action({"key": "major", "value": "人工智能"}, evidence="人工智能"))

    container, session = await _container_with_model(save)
    await container.profile_service.update_field(
        "u1", "major", "数学", confidence=0.9, source="conversation"
    )
    await _send(container, session, "人工智能")
    conflict = (await container.profile_service.list_conflicts("u1"))[0]
    resolved = await container.profile_service.resolve_conflict(
        "u1", conflict.id, choice="revision"
    )
    assert resolved.status is ProfileEntryStatus.SUPERSEDED
    current = next(f for f in await container.profile_service.get_fields("u1") if f.key == "major")
    assert current.value == "人工智能"
    assert await container.profile_service.list_conflicts("u1") == []


@pytest.mark.asyncio
async def test_resolving_with_current_keeps_the_record_and_marks_proposal_withdrawn() -> None:
    async def save(runtime) -> None:
        await runtime.action(_action({"key": "major", "value": "人工智能"}, evidence="人工智能"))

    container, session = await _container_with_model(save)
    await container.profile_service.update_field(
        "u1", "major", "数学", confidence=0.9, source="conversation"
    )
    await _send(container, session, "人工智能")
    conflict = (await container.profile_service.list_conflicts("u1"))[0]
    resolved = await container.profile_service.resolve_conflict(
        "u1", conflict.id, choice="current"
    )
    assert resolved.status is ProfileEntryStatus.WITHDRAWN
    current = next(f for f in await container.profile_service.get_fields("u1") if f.key == "major")
    assert current.value == "数学"


@pytest.mark.asyncio
async def test_deletion_keeps_a_withdrawn_history_row() -> None:
    container, _ = await _container_with_model()
    await container.profile_service.correct_field("u1", "major", "数学")
    await container.profile_service.drop_field("u1", "major")
    history = await container.profile_service.list_revisions("u1", "major")
    assert history and history[-1].status is ProfileEntryStatus.WITHDRAWN
    assert await container.profile_service.get_fields("u1", ["major"]) == []


@pytest.mark.asyncio
async def test_facade_exposes_history_and_conflict_resolution() -> None:
    """API 层只追加：历史可回读、冲突可裁定，旧 workspace 投影仍只有当前值。"""
    from zhiyin_api.dto.workspace import ProfileConflictResolveRequest

    async def save(runtime) -> None:
        await runtime.action(_action({"key": "major", "value": "人工智能"}, evidence="人工智能"))

    container, session = await _container_with_model(save)
    await container.profile_service.update_field(
        "u1", "major", "数学", confidence=0.9, source="conversation"
    )
    await _send(container, session, "人工智能")
    history = await container.facade.list_profile_history("u1", "major")
    assert any(item.status is ProfileEntryStatus.CONFLICT for item in history)
    conflict = next(item for item in history if item.status is ProfileEntryStatus.CONFLICT)
    resolved = await container.facade.resolve_profile_conflict(
        "u1", conflict.id, ProfileConflictResolveRequest(choice="revision")
    )
    assert resolved.key == "major"
    assert resolved.status is ProfileEntryStatus.SUPERSEDED
    current = next(f for f in await container.profile_service.get_fields("u1") if f.key == "major")
    assert current.value == "人工智能"


@pytest.mark.asyncio
async def test_resolve_rejects_unknown_or_invalid_choice() -> None:
    container, _ = await _container_with_model()
    with pytest.raises(InvalidRequest):
        await container.profile_service.resolve_conflict("u1", "missing", choice="whatever")
    with pytest.raises(ResourceNotFound):
        await container.profile_service.resolve_conflict("u1", "missing", choice="revision")
