"""画像写入路径：原话引用、类型属性、时间范围与长度口径。

《个人画像设计-2026-10-20》第 3.1/4 节要求：写入方只给「键、整理后的内容、来源与依据」，
类别/属性/核实状态/有效范围由服务端校验后固化；原话引用要指向真实本轮消息。
上一版只有服务层支持这些字段，对话工具链路没有把它们传下来 —— 这里锁住端到端。
"""

from __future__ import annotations

import pytest

from tests.e2e.test_main_path import _container
from zhiyin_business.services.dialogue_runtime import active_dialogue
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_kernel.enums import ProfileEntryType, ProfileVerification
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_orchestration import AgentResult


class _Model:
    def __init__(self, callback) -> None:
        self.callback = callback
        self.text = "记下了。"

    async def invoke(self, request):
        await self.callback(active_dialogue.get())
        return AgentResult(agent_id=request.agent_id, raw_text=self.text, valid=True)


async def _setup(callback):
    container = _container()
    from zhiyin_business.services.dynamic_config import load_snapshot

    await load_snapshot(container.registry_service)
    container.orchestrator._agent_engine = _Model(callback)
    session = await container.orchestrator.enter_task("u1", "free_chat")
    return container, session


async def _send(container, session, text="继续", **kwargs):
    return await container.orchestrator.handle_message(
        TurnRequest(user_id="u1", task_id=session.id, message=text, **kwargs)
    )


def _profile_action(payload: dict, *, evidence: str, authorization: str = "automatic") -> dict:
    return {
        "operation": "profile.update",
        "payload": {**payload, "assertion_type": "affirmative_self_statement"},
        "authorization": authorization,
        "evidence": evidence,
    }


@pytest.mark.asyncio
async def test_conversation_write_carries_attributes_and_origin_turn() -> None:
    """兴趣的正负/情境与“原话来自哪一轮”必须随真实对话写入。"""

    async def callback(runtime) -> None:
        await runtime.action(
            _profile_action(
                {
                    "key": "interest",
                    "value": ["调试程序"],
                    "attributes": {"polarity": "like", "context": "一次文件读取的调试"},
                },
                evidence="我喜欢把程序调通",
            )
        )

    container, session = await _setup(callback)
    await _send(container, session, "我喜欢把程序调通")
    field = next(f for f in await container.profile_service.get_fields("u1") if f.key == "interest")
    assert field.entry_type is ProfileEntryType.INTEREST
    assert field.attributes == {"polarity": "like", "context": "一次文件读取的调试"}
    assert field.verification is ProfileVerification.SELF_REPORTED
    assert field.origin_ref.startswith(f"conversation:{session.id}:")
    assert field.value == ["调试程序"]


@pytest.mark.asyncio
async def test_conversation_write_carries_valid_range_without_filling_unknown_time() -> None:
    """临时条件要能带有效范围；没给时间时不能自动补成当前时间。"""

    async def callback(runtime) -> None:
        await runtime.action(
            _profile_action(
                {
                    "key": "constraints",
                    "value": "本周只有晚上有空",
                    "attributes": {"scope": "本周"},
                    "valid_from": "2026-10-20T00:00:00+08:00",
                    "valid_to": "2026-10-26T23:59:59+08:00",
                },
                evidence="本周只有晚上有空",
            )
        )

    container, session = await _setup(callback)
    await _send(container, session, "本周只有晚上有空")
    field = next(f for f in await container.profile_service.get_fields("u1") if f.key == "constraints")
    assert field.entry_type is ProfileEntryType.CONDITION
    assert field.valid_from is not None and field.valid_to is not None
    assert field.attributes["scope"] == "本周"
    # 事件时间没有提供 → 保持未知，不补当前时间。
    assert field.event_at is None


@pytest.mark.asyncio
async def test_long_experience_is_not_blocked_by_the_old_2000_char_precheck() -> None:
    """经历正文允许 12000 字；对话预检不能再单独卡 2000 字。"""

    long_text = "项目" * 1500

    async def callback(runtime) -> None:
        await runtime.action(
            _profile_action({"key": "experience", "value": long_text}, evidence="我做过一个长项目")
        )

    container, session = await _setup(callback)
    await _send(container, session, "我做过一个长项目")
    field = next(f for f in await container.profile_service.get_fields("u1") if f.key == "experience")
    assert field.value == long_text
    assert len(field.value) > 2000


@pytest.mark.asyncio
async def test_automatic_write_requires_affirmative_assertion_type() -> None:
    """引述/假设/不确定不能通过自动记忆写成本人事实。"""

    async def callback(runtime) -> None:
        await runtime.action(
            {
                "operation": "profile.update",
                "payload": {
                    "key": "major",
                    "value": "计算机",
                    "assertion_type": "quoted",
                },
                "authorization": "automatic",
                "evidence": "同学说计算机",
            }
        )

    container, session = await _setup(callback)
    with pytest.raises(InvalidRequest):
        await _send(container, session, "同学说计算机")
    assert not await container.profile_service.get_fields("u1", ["major"])


@pytest.mark.asyncio
async def test_invalid_attributes_are_rejected_before_write() -> None:
    """类型属性来自受控取值，模型不能自由扩展。"""

    async def callback(runtime) -> None:
        await runtime.action(
            _profile_action(
                {"key": "interest", "value": "调试程序", "attributes": {"polarity": "love"}},
                evidence="我喜欢调试程序",
            )
        )

    container, session = await _setup(callback)
    with pytest.raises(InvalidRequest):
        await _send(container, session, "我喜欢调试程序")
    assert not await container.profile_service.get_fields("u1", ["interest"])


@pytest.mark.asyncio
async def test_exploration_hypotheses_are_stored_as_separate_clues() -> None:
    """设计第 3.2 节：探索里的“可能……”单独保存为线索，并带本会话原话依据。"""
    calls = {"n": 0}

    async def callback(runtime) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            return
        turn_id = next(iter(runtime.exploration_sources))
        await runtime.record_exploration(
            {
                "goal": "了解兴趣",
                "mode": "explore",
                "statements": [{"turn_id": turn_id, "quote": "我喜欢调试程序"}],
                "hypotheses": ["可能更关注弄清原因的过程"],
                "explored_topics": ["调试"],
                "open_questions": [],
                "next_focus": "继续了解具体经历",
            }
        )

    container, session = await _setup(callback)
    await _send(container, session, "我喜欢调试程序")
    await container.profile_service.update_field(
        "u1", "interest", ["调试程序"], confidence=0.9, source="conversation",
        origin_ref=f"conversation:{session.id}:turn-1",
    )
    await _send(container, session, "嗯")
    clues = await container.profile_service.get_clues("u1")
    assert [clue.text for clue in clues] == ["可能更关注弄清原因的过程"]
    assert clues[0].session_id == session.id
    assert clues[0].evidence == ["我喜欢调试程序"]
    assert clues[0].field_keys == ["interest"]
    assert clues[0].status.value == "proposed"


@pytest.mark.asyncio
async def test_existing_clue_does_not_borrow_the_latest_turn_quote() -> None:
    """A hypothesis that survives a turn keeps its original evidence."""
    calls = {"n": 0}

    async def callback(runtime) -> None:
        calls["n"] += 1
        turn_id = list(runtime.exploration_sources)[-1]
        quote = "我喜欢调试程序" if calls["n"] == 1 else "嗯"
        await runtime.record_exploration({
            "goal": "了解兴趣",
            "mode": "explore",
            "statements": [{"turn_id": turn_id, "quote": quote}],
            "hypotheses": ["可能更关注弄清原因的过程"],
            "explored_topics": ["调试"],
            "open_questions": [],
            "next_focus": "继续了解具体经历",
        })

    container, session = await _setup(callback)
    await _send(container, session, "我喜欢调试程序")
    await _send(container, session, "嗯")
    clues = await container.profile_service.get_clues("u1")
    assert [clue.evidence for clue in clues] == [["我喜欢调试程序"]]


@pytest.mark.asyncio
async def test_report_operation_turn_cannot_replace_clue_evidence() -> None:
    """生成/保存/启用报告是操作指令，不能成为“用户原话”证据。"""
    calls = {"n": 0}
    prompt = "请根据我更新后的资料重新生成一份报告草稿，先保存草稿，不要生效。"

    async def callback(runtime) -> None:
        calls["n"] += 1
        turn_id = list(runtime.exploration_sources)[-1]
        quote = "我喜欢调试程序" if calls["n"] == 1 else prompt
        await runtime.record_exploration({
            "goal": "了解兴趣",
            "mode": "explore",
            "statements": [{"turn_id": turn_id, "quote": quote}],
            "hypotheses": ["可能更关注弄清原因的过程"],
            "explored_topics": ["调试"],
            "open_questions": [],
            "next_focus": "继续了解具体经历",
        })

    container, session = await _setup(callback)
    await _send(container, session, "我喜欢调试程序")
    await _send(container, session, prompt)
    clues = await container.profile_service.get_clues("u1")
    assert [clue.evidence for clue in clues] == [["我喜欢调试程序"]]


@pytest.mark.asyncio
async def test_legacy_operation_evidence_is_not_shown_as_user_provenance() -> None:
    from datetime import datetime, timezone
    from zhiyin_kernel.blackboard import ProfileClue

    container, _ = await _setup(lambda runtime: None)
    now = datetime.now(timezone.utc)
    await container.profile_service.replace_session_clues("u1", "s1", [ProfileClue(
        id="", user_id="u1", session_id="s1", text="可能更关注弄清原因的过程",
        evidence=[
            "请根据我更新后的资料重新生成一份报告草稿，先保存草稿，不要生效。",
            "请根据我的已有资料，为我生成一份方向方案，依据不足的部分请标为待核实",
            "我喜欢调试程序",
        ],
        field_keys=["interest"], source="assessment", created_at=now, updated_at=now,
    )])
    clues = await container.profile_service.get_clues("u1")
    assert clues[0].evidence == ["我喜欢调试程序"]
    # The workspace DTO also reads profile.clues, not only get_clues().
    profile = await container.profile_service.get("u1")
    assert profile.clues[0].evidence == ["我喜欢调试程序"]


def test_direction_and_report_generation_prompts_are_operations_not_provenance() -> None:
    from zhiyin_business.services.dialogue_exploration import is_operation_message

    assert is_operation_message("请根据我的已有资料，为我生成一份方向方案，依据不足的部分请标为待核实")
    assert is_operation_message("请根据我最新资料生成诊断报告草稿；先保存草稿，不要直接生效。")
    assert not is_operation_message("我喜欢数据分析，也做过一个课程项目")


@pytest.mark.asyncio
async def test_content_level_denial_blocks_the_automatic_extraction_from_that_message() -> None:
    """“这条不要记录”：同一条消息及其派生的自动写入被服务端策略拦住，其他内容不受影响。"""
    from zhiyin_business.services.conversation_ledger import digest
    from zhiyin_business.services.memory_policy import MemoryPolicyService

    async def callback(runtime) -> None:
        await runtime.action(
            _profile_action({"key": "interest", "value": "调试程序"}, evidence="我喜欢调试程序")
        )

    container, session = await _setup(callback)
    fingerprint = digest({"user_id": "u1", "message": "我喜欢调试程序"})
    await MemoryPolicyService(container.student_state).deny_content(
        "u1", fingerprint, source="conversation", note="这条内容不要记录"
    )
    with pytest.raises(InvalidRequest):
        await _send(container, session, "我喜欢调试程序")
    assert not await container.profile_service.get_fields("u1", ["interest"])


@pytest.mark.asyncio
async def test_single_save_authorization_does_not_restore_other_automatic_writes() -> None:
    """“只保存这一条”：只放行点名的键，其他自动记录继续关闭。"""
    from zhiyin_business.services.memory_policy import MemoryPolicyService

    async def save_one(runtime) -> None:
        await runtime.action(
            {
                "operation": "profile.update",
                "payload": {
                    "key": "major",
                    "value": "人工智能",
                    "assertion_type": "explicit_correction",
                    "save_scope": "single",
                },
                "authorization": "explicit",
                "evidence": "只保存人工智能这一条",
            }
        )

    container, session = await _setup(save_one)
    await _send(container, session, "只保存人工智能这一条")
    snapshot = await MemoryPolicyService(container.student_state).snapshot("u1", session.id)
    assert snapshot["single_only"] is True
    assert snapshot["single_keys"] == ["major"]
    assert next(f for f in await container.profile_service.get_fields("u1") if f.key == "major").value == "人工智能"

    # 别的键：自动写入仍被拒绝。
    async def write_interest(runtime) -> None:
        await runtime.action(
            _profile_action({"key": "interest", "value": "调试程序"}, evidence="我喜欢调试程序")
        )

    container.orchestrator._agent_engine = _Model(write_interest)
    with pytest.raises(InvalidRequest):
        await _send(container, session, "我喜欢调试程序")
    assert not await container.profile_service.get_fields("u1", ["interest"])

