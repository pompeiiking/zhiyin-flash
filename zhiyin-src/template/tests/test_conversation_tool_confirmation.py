import pytest

from tests.test_conversation_asset_confirmation import Engine, send, setup
from zhiyin_business.services.tool_offers import TOOL_OFFERS, mentioned_tasks, task_offer
from zhiyin_kernel.assets import ActionPhase, ActionPlan, ActionTask


class SuggestingEngine(Engine):
    def __init__(self, proposal="read_academic", succeeds=True):
        super().__init__()
        self.proposal = proposal
        self.succeeds = succeeds

    async def conversation_tool_names(self, agent_id):
        return {"workspace.read", "workspace.task.set_done", "web.search"}

    async def invoke(self, request):
        result = await super().invoke(request)
        result.structured["tool_offer"] = self.proposal
        if request.prompt_vars.get("confirmed_tool_request") and self.succeeds:
            if self.proposal == "task_done":
                result.business_tool_calls = ["workspace.task.set_done"]
                result.business_tool_receipts = [{"executed": True, "task": "整理项目经历", "done": True}]
            else:
                result.business_tool_calls = ["workspace.read"]
                result.business_read_receipts = [{"area": "academic", "text": "成绩记录：数学：90"}]
        return result


def test_tool_registry_covers_all_current_tool_names():
    expected = {"workspace.read", "workspace.task.set_done", "web.search", "kb.search",
                "xuezhi.search", "profile.read", "behavior.recent", "plan.read", "chart.render",
                "action_progress.read", "plan_progress_skill.read"}
    assert {offer.tool for offer in TOOL_OFFERS.values()} | {task_offer("任务").tool} == expected


def test_task_reference_supports_long_names_and_rejects_ambiguous_fragments():
    plan = ActionPlan(id="p", phases=[ActionPhase(name="本周", date_range="", tasks=[
        ActionTask(text="查看「软件测试实习」招聘信息并整理要求与注意事项，" * 4),
        ActionTask(text="查看软件测试社团活动并整理要求"),
    ])])
    assert mentioned_tasks(plan, "我已经做完查看「软件测试实习」招聘信息") == [plan.phases[0].tasks[0]]
    assert len(mentioned_tasks(plan, "我已经做完软件测试")) == 0  # too short to identify safely
    assert len(task_offer(plan.phases[0].tasks[0].text).question) < 80


@pytest.mark.asyncio
async def test_offer_is_confirmed_in_same_conversation_and_uses_real_tool_path():
    c, _, session = await setup()
    engine = SuggestingEngine()
    c.orchestrator._agent_engine = engine
    first = await send(c, session, "我觉得课程有些吃力")
    assert first.messages[0].text.endswith(TOOL_OFFERS["read_academic"].question)
    second = await send(c, session, "可以")
    assert engine.requests[-1].prompt_vars["confirmed_tool_request"] == TOOL_OFFERS["read_academic"].instruction
    assert "我觉得课程有些吃力" in engine.requests[-1].prompt_vars["user_input"]
    assert "未能确认" not in second.messages[0].text
    assert (await c.memory_service.list_turns("u1", session.id))[-2].text == "可以"


@pytest.mark.asyncio
async def test_decline_or_other_conversation_never_runs_proposal():
    c, _, session = await setup()
    engine = SuggestingEngine()
    c.orchestrator._agent_engine = engine
    await send(c, session, "课程有些吃力")
    await send(c, session, "先不要")
    assert "confirmed_tool_request" not in engine.requests[-1].prompt_vars
    again = await send(c, session, "课程仍然有些吃力")
    assert not again.messages[0].text.endswith(TOOL_OFFERS["read_academic"].question)
    other = await c.orchestrator.enter_task("u1", "confused")
    await send(c, other, "可以")
    assert "confirmed_tool_request" not in engine.requests[-1].prompt_vars


@pytest.mark.asyncio
async def test_explicit_refusal_does_not_enable_tool_calling():
    c, _, session = await setup()
    engine = SuggestingEngine()
    c.orchestrator._agent_engine = engine
    result = await send(c, session, "不要查询我的成绩，我们聊聊别的")
    assert engine.requests[-1].prompt_vars["proposal_only"] is True
    assert not result.messages[0].text.endswith(TOOL_OFFERS["read_academic"].question)


@pytest.mark.asyncio
async def test_completed_direct_query_is_not_offered_again():
    class DirectQueryEngine(SuggestingEngine):
        async def invoke(self, request):
            result = await super().invoke(request)
            result.business_tool_calls = ["workspace.read"]
            result.business_read_receipts = [{"area": "academic", "text": "没有成绩记录"}]
            return result
    c, _, session = await setup()
    c.orchestrator._agent_engine = DirectQueryEngine()
    result = await send(c, session, "请查询我的成绩")
    assert not result.messages[0].text.endswith(TOOL_OFFERS["read_academic"].question)


@pytest.mark.asyncio
async def test_failed_tool_is_not_claimed_as_success():
    c, _, session = await setup()
    c.orchestrator._agent_engine = SuggestingEngine(succeeds=False)
    await send(c, session, "课程有些吃力")
    result = await send(c, session, "可以")
    assert "未能确认" in result.messages[0].text


@pytest.mark.asyncio
async def test_old_option_cannot_confirm_a_different_offer():
    c, _, session = await setup()
    engine = SuggestingEngine()
    c.orchestrator._agent_engine = engine
    await send(c, session, "课程有些吃力")
    await send(c, session, "可以", option_id="tool.web.accept", option_value="accept")
    assert "confirmed_tool_request" not in engine.requests[-1].prompt_vars


@pytest.mark.asyncio
async def test_uninstalled_tool_is_not_offered_even_if_model_suggests_it():
    c, _, session = await setup()
    engine = SuggestingEngine("chart_plan")
    c.orchestrator._agent_engine = engine
    result = await send(c, session, "计划进行得如何")
    assert not result.messages[0].text.endswith(TOOL_OFFERS["chart_plan"].question)


@pytest.mark.asyncio
async def test_proposal_metadata_does_not_break_plan_creation():
    c, _, session = await setup()
    c.orchestrator._agent_engine = SuggestingEngine()
    result = await send(c, session, "请帮我制定行动计划")
    assert await c.asset_service.get_action_plan("u1") is not None
    assert "行动计划已生成" in result.messages[0].text


@pytest.mark.asyncio
async def test_proposal_metadata_does_not_break_report_creation():
    c, _, session = await setup()
    c.orchestrator._agent_engine = SuggestingEngine()
    result = await send(c, session, "请生成诊断报告")
    assert await c.asset_service.get_report("u1") is not None
    assert "诊断报告已生成" in result.messages[0].text


@pytest.mark.asyncio
async def test_task_offer_only_names_one_existing_unfinished_task():
    c, _, session = await setup()
    engine = SuggestingEngine("task_done")
    c.orchestrator._agent_engine = engine
    await c.asset_service.save_action_plan("u1", ActionPlan(id="p", phases=[ActionPhase(
        name="本周", date_range="", tasks=[ActionTask(text="整理项目经历", done=False)])]))
    first = await send(c, session, "我已经做完整理项目经历")
    assert first.messages[0].text.endswith(task_offer("整理项目经历").question)
    result = await send(c, session, "可以")
    assert engine.requests[-1].prompt_vars["raw_user_message"] == "请把整理项目经历标记为完成。"
    assert "已将「整理项目经历」标记为完成" in result.messages[0].text


@pytest.mark.asyncio
async def test_task_completion_statement_is_offered_even_without_model_selection():
    c, _, session = await setup()
    c.orchestrator._agent_engine = SuggestingEngine("")
    await c.asset_service.save_action_plan("u1", ActionPlan(id="p", phases=[ActionPhase(
        name="本周", date_range="", tasks=[ActionTask(text="整理项目经历", done=False)])]))
    result = await send(c, session, "我已经做完整理项目经历")
    assert result.messages[0].text.endswith(task_offer("整理项目经历").question)


@pytest.mark.asyncio
async def test_task_changed_in_another_tab_does_not_execute_old_proposal():
    c, _, session = await setup()
    engine = SuggestingEngine("task_done")
    c.orchestrator._agent_engine = engine
    await c.asset_service.save_action_plan("u1", ActionPlan(id="p", phases=[ActionPhase(
        name="本周", date_range="", tasks=[ActionTask(text="整理项目经历", done=False)])]))
    await send(c, session, "我已经做完整理项目经历")
    await c.asset_service.save_action_plan("u1", ActionPlan(id="p", phases=[ActionPhase(
        name="本周", date_range="", tasks=[ActionTask(text="整理项目经历", done=True)])]))
    result = await send(c, session, "可以")
    assert "这次没有修改" in result.messages[0].text
    assert len(engine.requests) == 1


@pytest.mark.asyncio
async def test_read_response_does_not_authorize_task_write():
    c, _, session = await setup()
    engine = SuggestingEngine("task_done")
    c.orchestrator._agent_engine = engine
    await c.asset_service.save_action_plan("u1", ActionPlan(id="p", phases=[ActionPhase(
        name="本周", date_range="", tasks=[ActionTask(text="整理项目经历", done=False)])]))
    await send(c, session, "我已经做完整理项目经历")
    await send(c, session, "看一下")
    assert "confirmed_tool_request" not in engine.requests[-1].prompt_vars
