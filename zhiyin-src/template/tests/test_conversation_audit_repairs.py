"""User-visible regressions from the 2026-10-19 conversation audit."""
import asyncio

import pytest

from tests.test_conversation_asset_confirmation import send, setup
from tests.test_conversation_task_actions import _setup_with_plan
from zhiyin_business.ports.orchestrator import IntentType
from zhiyin_business.services.orchestrator import _explicit_direction_request, _is_safety_blocked


@pytest.mark.asyncio
async def test_sensitive_text_never_reaches_model_or_history():
    c, engine, session = await setup()
    message = "我的手机号13800000000，我喜欢Python，请分析"
    result = await send(c, session, message)
    assert not engine.requests
    turns = await c.memory_service.list_turns("u1", session.id)
    assert all("13800000000" not in turn.model_dump_json() for turn in turns)
    assert "未交给模型" in result.messages[0].text
    assert await c.profile_service.get("u1") is None


@pytest.mark.asyncio
async def test_sensitive_attachment_is_not_sent_or_recorded():
    c, engine, session = await setup()
    await send(c, session, "看材料", attachment_text="手机号13800000000", attachment_name="材料.txt")
    assert not engine.requests
    assert "13800000000" not in str(await c.memory_service.list_turns("u1", session.id))


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["不要把我的专业改为法学", "我的专业不是法学，请不要改专业"])
async def test_negated_correction_preserves_profile(message):
    c, _, session = await setup()
    await c.profile_service.update_field("u1", "major", "计算机", confidence=1, source="user_edit")
    await send(c, session, message)
    assert (await c.profile_service.get_fields("u1", ["major"]))[0].value == "计算机"


@pytest.mark.asyncio
async def test_negative_year_is_not_used_as_new_year():
    c, _, session = await setup()
    await c.profile_service.update_field("u1", "study_year", "大三", confidence=1, source="user_edit")
    await send(c, session, "我不是大二")
    assert (await c.profile_service.get_fields("u1", ["study_year"]))[0].value == "大三"


@pytest.mark.asyncio
async def test_correction_preserves_system_and_agent_turn_and_replays_all():
    c, engine, session = await setup()
    first = await send(c, session, "把专业改成法学", client_msg_id="correct-1")
    saved = await c.memory_service.list_turns("u1", session.id)
    assert [t.role for t in saved] == ["user", "system", "agent"]
    count = len(engine.requests)
    second = await send(c, session, "把专业改成法学", client_msg_id="correct-1")
    assert second == first
    assert len(engine.requests) == count


@pytest.mark.asyncio
async def test_concurrent_retries_only_run_once():
    c, engine, session = await setup()
    original = engine.invoke
    async def delayed(request):
        await asyncio.sleep(.02)
        return await original(request)
    engine.invoke = delayed
    first, second = await asyncio.gather(
        send(c, session, "继续聊", client_msg_id="same"),
        send(c, session, "继续聊", client_msg_id="same"),
    )
    assert first == second
    assert len(engine.requests) == 1
    assert len([t for t in await c.memory_service.list_turns("u1", session.id) if t.role == "agent"]) == 1


@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_for_changed_content():
    c, _, session = await setup()
    await send(c, session, "继续聊", client_msg_id="same")
    with pytest.raises(Exception, match="内容已经变化"):
        await send(c, session, "生成行动计划", client_msg_id="same")
    assert await c.asset_service.get_action_plan("u1") is None


@pytest.mark.asyncio
async def test_negated_task_does_not_complete():
    c, _, session = await _setup_with_plan("整理项目", "核对要求")
    await send(c, session, "第一项不要完成")
    plan = await c.asset_service.get_action_plan("u1")
    assert not any(t.done for p in plan.phases for t in p.tasks)


@pytest.mark.asyncio
async def test_mixed_task_states_are_applied_per_clause():
    c, _, session = await _setup_with_plan("整理项目", "核对要求")
    await c.asset_service.mark_action_task_done("u1", "task_1", done=True)
    await send(c, session, "第一项完成了，第二项还没做完")
    tasks = (await c.asset_service.get_action_plan("u1")).phases[0].tasks
    assert [t.done for t in tasks] == [True, False]


@pytest.mark.asyncio
async def test_partial_failure_reports_successful_and_failed_items():
    c, _, session = await _setup_with_plan("整理项目", "核对要求")
    original = c.asset_service.mark_action_task_done
    async def mark(user_id, task_id, **kwargs):
        if task_id == "task_1":
            raise RuntimeError("synthetic write failure")
        return await original(user_id, task_id, **kwargs)
    c.orchestrator._assets.mark_action_task_done = mark
    result = await send(c, session, "第一项和第二项都完成了")
    text = result.messages[0].text
    assert "已把「整理项目」标记为完成" in text
    assert "未能保存：「核对要求」" in text
    assert [t.done for t in (await c.asset_service.get_action_plan("u1")).phases[0].tasks] == [True, False]


@pytest.mark.asyncio
async def test_task_write_does_not_drop_followup_question():
    c, engine, session = await _setup_with_plan("整理项目", "核对要求")
    result = await send(c, session, "第一项完成了，接下来怎么做？")
    assert (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].done
    assert engine.requests[-1].prompt_vars["confirmed_task_result"]
    assert "标记为完成" in result.messages[0].text


@pytest.mark.asyncio
async def test_long_history_retains_tail_constraints_and_multiple_rounds():
    c, engine, session = await setup()
    fact = "先说明一下我的背景。" * 8 + "我每周只有两小时，不考虑考研，也不要推荐付费课程。"
    await send(c, session, fact)
    for _ in range(5):
        await send(c, session, "继续聊")
    history = engine.requests[-1].prompt_vars["turn_group"]
    assert any(fact in line for line in history)
    assert engine.requests[-1].conversation
    assert "swot" not in engine.requests[-1].output_schema["properties"]


@pytest.mark.asyncio
async def test_old_offer_is_invalid_after_topic_change():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    await send(c, session, "实习接下来怎么做")
    await send(c, session, "先聊聊我最近的心情")
    await send(c, session, "可以")
    assert await c.asset_service.get_action_plan("u1") is None


@pytest.mark.asyncio
async def test_plain_agreement_after_progress_offer_creates_plan():
    c, _, session = await setup()
    await send(c, session, "计划进度怎么样了")
    await send(c, session, "可以")
    assert await c.asset_service.get_action_plan("u1") is not None


@pytest.mark.asyncio
async def test_reminder_phrase_does_not_hide_saved_plan():
    c, _, session = await setup()
    result = await send(c, session, "请生成行动计划，明天完成项目整理")
    assert await c.asset_service.get_action_plan("u1") is not None
    assert "行动计划已生成" in result.messages[0].text


def test_legitimate_direct_generation_is_not_injection():
    assert not _is_safety_blocked("请直接生成诊断报告")
    assert not _is_safety_blocked("老师建议我做数据分析，我想生成报告")
    assert _explicit_direction_request("请先生成三个职业方向")


@pytest.mark.asyncio
async def test_verified_constraints_survive_the_recent_history_window():
    from tests.test_conversation_asset_confirmation import Engine
    c, _, session = await setup()
    class FactEngine(Engine):
        async def invoke(self, request):
            result = await super().invoke(request)
            if request.prompt_vars.get("raw_user_message") == "我每周只有两小时":
                result.structured["memory_updates"] = [{"key": "time_budget", "value": "每周只有两小时", "evidence": "我每周只有两小时"}]
            return result
    engine = FactEngine()
    c.orchestrator._agent_engine = engine
    await send(c, session, "我每周只有两小时")
    for _ in range(14):
        await send(c, session, "继续聊")
    variables = engine.requests[-1].prompt_vars
    assert not any("只有两小时" in text for text in variables["turn_group"])
    assert variables["conversation_facts"]["time_budget"]["value"] == "每周只有两小时"


@pytest.mark.asyncio
async def test_model_cannot_store_an_invented_constraint():
    from tests.test_conversation_asset_confirmation import Engine
    c, _, session = await setup()
    class FactEngine(Engine):
        async def invoke(self, request):
            result = await super().invoke(request)
            result.structured["memory_updates"] = [{"key": "preference", "value": "愿意付费", "evidence": "我愿意付费"}]
            return result
    engine = FactEngine()
    c.orchestrator._agent_engine = engine
    await send(c, session, "先聊聊")
    await send(c, session, "继续聊")
    assert not engine.requests[-1].prompt_vars["conversation_facts"]


def test_old_sensitive_records_are_redacted_only_at_model_boundary():
    from zhiyin_orchestration import AgentRequest
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    request = AgentRequest(agent_id="test", blackboard={"profile": {"experience": "旧记录13800000000"}},
        prompt_vars={"user_input": "继续聊", "turn_group": ["旧记录13800000000"]})
    text = AgnoAgentEngine(model_factory=lambda: None)._compose_input(request, {})
    assert "13800000000" not in text
    assert "敏感信息已隐藏" in text
    assert request.blackboard["profile"]["experience"] == "旧记录13800000000"


@pytest.mark.asyncio
async def test_old_button_cannot_confirm_a_new_proposal():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    first = await send(c, session, "实习接下来怎么做")
    old_value = first.guide.options[0].value
    await send(c, session, "先聊心情")
    current = await send(c, session, "给我看行动计划")
    assert current.guide.options[0].value != old_value
    result = await send(c, session, "可以", option_id="asset.plan.accept", option_value=old_value)
    assert "已过期" in result.messages[0].text
    assert await c.asset_service.get_action_plan("u1") is None
