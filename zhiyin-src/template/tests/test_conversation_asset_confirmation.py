"""Conversation offers must be tied to a real, immediately preceding question."""

from unittest.mock import AsyncMock

import pytest

from tests.e2e.test_main_path import _container
from zhiyin_business.policies.collection_gate import CollectionGate
from zhiyin_business.policies.routing import IntentDecision
from zhiyin_business.ports.orchestrator import IntentType, TurnRequest
from zhiyin_business.services.orchestrator import (
    _ASSET_OFFERS, _explicit_plan_request, _explicit_report_request, _offer_answer,
)
from zhiyin_kernel.enums import AssetType
from zhiyin_orchestration import AgentResult


class Engine:
    def __init__(self, valid=True):
        self.valid = valid
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        if not self.valid:
            return AgentResult(agent_id=request.agent_id, valid=False, structured={})
        if request.stage == "diagnose":
            body = {"conclusion": "先核对现有情况。", "verdict": {"title": "先核对", "summary": "根据现有情况继续了解。"},
                    "swot": {"strength": [], "weakness": [], "opportunity": [], "risk": []},
                    "guide": {"kind": "question", "text": "继续了解"}}
        elif request.stage == "act":
            body = {"conclusion": "可以先整理已有项目。", "phases": [{"name": "本周", "date_range": "本周",
                    "tasks": [{"text": "整理项目经历"}]}], "guide": {"kind": "question", "text": "继续"}}
        else:
            body = {"conclusion": "我们先了解一下。", "field_updates": [], "remaining_gaps": [],
                    "guide": {"kind": "question", "text": "继续"}}
        return AgentResult(agent_id=request.agent_id, valid=True, structured=body)


class ReadingEngine(Engine):
    async def invoke(self, request):
        result = await super().invoke(request)
        result.business_tool_calls = ["workspace.read"]
        return result


async def setup(intent=IntentType.FREE_CHAT, *, ready=False):
    container = _container()
    engine = Engine()
    orchestrator = container.orchestrator
    orchestrator._agent_engine = engine
    orchestrator._intent_policy.classify_with_decision = AsyncMock(return_value=IntentDecision(intent=intent))
    orchestrator.collection_gate = AsyncMock(return_value=CollectionGate(ready, 1 if ready else 0, 0.8, ()))
    session = await orchestrator.enter_task("u1", "free_chat")
    return container, engine, session


async def send(container, session, message, **kwargs):
    return await container.orchestrator.handle_message(TurnRequest(user_id="u1", task_id=session.id, message=message, **kwargs))


@pytest.mark.parametrize("message", ["可以", "好的！", "嗯嗯", "同意", "生成吧", "可以，不过每周只有三小时"])
def test_explicit_affirmations(message):
    assert _offer_answer(message) == "accept"


@pytest.mark.parametrize("message", ["先不要", "不用。", "以后再说", "可以但先不要", "可以，但是我还没想好", "可以，但先别做", "可以，下次再做", "可以，每周两小时够吗？", "不知道"])
def test_refusal_and_ambiguous_responses_are_not_accepted(message):
    assert _offer_answer(message) != "accept"


@pytest.mark.parametrize("message", ["帮我看看报告", "不要生成报告", "不生成报告", "我的报告在哪里", "报告没有生成", "如何生成报告"])
def test_report_read_is_not_write_authorization(message):
    assert not _explicit_report_request(message)


@pytest.mark.parametrize("message", ["给我看行动计划", "不生成计划", "请制定计划，但不要保存", "计划还没生成", "怎么生成计划"])
def test_plan_read_is_not_write_authorization(message):
    assert not _explicit_plan_request(message)


def test_uncertainty_does_not_negate_an_explicit_report_request():
    assert _explicit_report_request("我不清楚方向，请生成诊断报告")


@pytest.mark.asyncio
async def test_offer_plan_then_confirm_creates_real_plan_and_preserves_original_turn():
    c, engine, session = await setup(IntentType.HOW_TO_ACT)
    first = await send(c, session, "实习接下来怎么做")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["plan"])
    assert await c.asset_service.get_action_plan("u1") is None
    assert [o.label for o in first.guide.options] == ["可以", "先不要"]
    second = await send(c, session, "可以")
    plan = await c.asset_service.get_action_plan("u1")
    assert plan and plan.phases[0].tasks[0].text == "整理项目经历"
    assert any(v.asset_type == AssetType.ACTION_PLAN for v in second.asset_versions)
    assert "行动计划已生成" in second.messages[0].text
    assert "confirmed_request" in engine.requests[-1].prompt_vars
    assert (await c.memory_service.list_turns("u1", session.id))[-2].text == "可以"


@pytest.mark.asyncio
async def test_report_offer_confirmation_and_no_automatic_report():
    c, _, session = await setup(ready=True)
    first = await send(c, session, "聊聊我的情况")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["report"])
    assert await c.asset_service.get_report("u1") is None
    second = await send(c, session, "好的")
    assert await c.asset_service.get_report("u1") is not None
    assert any(v.asset_type == AssetType.REPORT for v in second.asset_versions)
    assert "诊断报告已生成" in second.messages[0].text


@pytest.mark.asyncio
async def test_decline_no_write_no_immediate_reoffer():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    await send(c, session, "实习接下来怎么做")
    result = await send(c, session, "先不要")
    assert await c.asset_service.get_action_plan("u1") is None
    assert not result.messages[0].text.endswith(_ASSET_OFFERS["plan"])
    again = await send(c, session, "实习接下来怎么做")
    assert not again.messages[0].text.endswith(_ASSET_OFFERS["plan"])


@pytest.mark.asyncio
async def test_agreement_in_another_conversation_is_not_authorization():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    await send(c, session, "实习接下来怎么做")
    from uuid import uuid4
    other = await c.orchestrator.enter_task("u1", "confused")
    assert other.id != session.id
    await send(c, other, "可以")
    assert await c.asset_service.get_action_plan("u1") is None


@pytest.mark.asyncio
async def test_failed_generation_is_reported_as_failure():
    c, engine, session = await setup(IntentType.HOW_TO_ACT)
    await send(c, session, "实习接下来怎么做")
    engine.valid = False
    result = await send(c, session, "可以")
    assert await c.asset_service.get_action_plan("u1") is None
    assert "没有成功生成行动计划" in result.messages[0].text
    assert not result.asset_versions


@pytest.mark.asyncio
async def test_direct_plan_request_works_without_previous_offer():
    c, _, session = await setup()
    result = await send(c, session, "请帮我制定行动计划")
    assert await c.asset_service.get_action_plan("u1") is not None
    assert "行动计划已生成" in result.messages[0].text


@pytest.mark.asyncio
async def test_accepted_constraints_reach_engine():
    c, engine, session = await setup(IntentType.HOW_TO_ACT)
    await send(c, session, "实习接下来怎么做")
    await send(c, session, "可以，不过每周只有三小时")
    assert await c.asset_service.get_action_plan("u1") is not None
    assert "每周只有三小时" in engine.requests[-1].prompt_vars["raw_user_message"]


@pytest.mark.asyncio
async def test_old_unrelated_option_does_not_confirm_current_offer():
    c, _, session = await setup(ready=True)
    await send(c, session, "聊聊我的情况")
    await send(c, session, "可以", option_id="asset.plan.accept", option_value="accept")
    assert await c.asset_service.get_report("u1") is None


@pytest.mark.asyncio
async def test_later_asset_from_another_tab_is_not_replaced():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    await send(c, session, "实习接下来怎么做")
    from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
    existing = ActionPlan(id="existing", phases=[ActionPhase(name="原计划", date_range="", tasks=[ActionTask(text="保留")])])
    await c.asset_service.save_action_plan("u1", existing)
    result = await send(c, session, "可以")
    plan = await c.asset_service.get_action_plan("u1")
    assert plan.phases[0].tasks[0].text == "保留"
    assert "没有重新生成" in result.messages[0].text


@pytest.mark.asyncio
async def test_reading_real_data_does_not_suppress_offers_or_confirmed_report():
    c, _, session = await setup(ready=True)
    c.orchestrator._agent_engine = ReadingEngine()
    first = await send(c, session, "聊聊我的情况")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["report"])
    result = await send(c, session, "可以")
    assert await c.asset_service.get_report("u1") is not None
    assert "诊断报告已生成" in result.messages[0].text


@pytest.mark.asyncio
async def test_reading_real_data_does_not_suppress_plan_offer():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    c.orchestrator._agent_engine = ReadingEngine()
    first = await send(c, session, "实习接下来怎么做")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["plan"])


@pytest.mark.asyncio
async def test_user_wants_to_keep_talking_does_not_get_pushed_to_report():
    c, _, session = await setup(ready=True)
    result = await send(c, session, "我想先聊聊现在的情况")
    assert not result.messages[0].text.endswith(_ASSET_OFFERS["report"])
    assert await c.asset_service.get_report("u1") is None


@pytest.mark.asyncio
async def test_no_plan_offer_without_a_concrete_goal():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    result = await send(c, session, "下一步怎么做")
    assert not result.messages[0].text.endswith(_ASSET_OFFERS["plan"])
    assert await c.asset_service.get_action_plan("u1") is None


@pytest.mark.asyncio
async def test_long_conversation_uses_the_latest_offer():
    c, _, session = await setup(IntentType.HOW_TO_ACT)
    from zhiyin_kernel.enums import LoopStage
    for index in range(205):
        await c.memory_service.record_turn("u1", session.id, role="agent", text=f"之前的回复 {index}", loop_stage=LoopStage.COLLECT)
    first = await send(c, session, "实习接下来怎么做")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["plan"])
    await send(c, session, "可以")
    assert await c.asset_service.get_action_plan("u1") is not None
