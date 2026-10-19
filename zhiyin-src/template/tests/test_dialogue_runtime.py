"""State/permission integration tests; scripted model decisions are not semantic evals."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from tests.e2e.test_main_path import _container
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_business.services.dialogue_runtime import active_dialogue
from zhiyin_business.services.conversation_ledger import ConversationLedger
from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_kernel.streaming import progress_channel
from zhiyin_orchestration import AgentResult


class Model:
    def __init__(self, callback=None, text="我们可以从高等数学的具体难点开始。"):
        self.callback, self.text, self.requests, self.receipts = callback, text, [], []

    async def invoke(self, request):
        self.requests.append(request)
        if self.callback:
            self.receipts.append(await self.callback(active_dialogue.get()))
        return AgentResult(agent_id=request.agent_id, raw_text=self.text, valid=True)


async def setup(callback=None):
    c = _container()
    from zhiyin_business.services.dynamic_config import load_snapshot
    await load_snapshot(c.registry_service)
    engine = Model(callback)
    c.orchestrator._agent_engine = engine
    session = await c.orchestrator.enter_task("u1", "free_chat")
    return c, engine, session


async def send(c, session, text="继续", **kwargs):
    return await c.orchestrator.handle_message(TurnRequest(user_id="u1", task_id=session.id, message=text, **kwargs))


def plan(text="整理课程笔记"):
    return ActionPlan(id="plan1", phases=[ActionPhase(name="本周", date_range="本周", tasks=[ActionTask(id="t1", text=text)])])


def action(op, payload, evidence="继续", authorization="explicit", **kw):
    return {"operation": op, "payload": ({**payload, "assertion_type": "affirmative_self_statement"} if op == "profile.update" else payload), "authorization": authorization, "evidence": evidence, **kw}


@pytest.mark.asyncio
async def test_natural_text_no_stage_contract_or_forced_guide():
    c, engine, s = await setup()
    r = await send(c, s, "高等数学")
    assert r.messages[-1].text == engine.text
    assert not r.guide.text and not r.guide.options
    assert engine.requests[-1].conversation and engine.requests[-1].output_schema is None
    assert engine.requests[-1].stage is None


@pytest.mark.asyncio
async def test_complete_recent_messages_and_short_answer_context():
    c, engine, s = await setup()
    first = "我每周只有两小时，不考研，不参加付费课。" + "我还有一个问题。" * 35
    await send(c, s, first)
    await send(c, s, "高等数学")
    assert engine.requests[-1].history[0]["content"] == first
    assert engine.requests[-1].prompt_vars["user_input"] == "高等数学"


@pytest.mark.asyncio
async def test_same_run_replays_without_new_model_or_write():
    c, engine, s = await setup()
    first = await send(c, s, client_msg_id="same")
    second = await send(c, s, client_msg_id="same")
    assert first == second and len(engine.requests) == 1
    with pytest.raises(InvalidRequest):
        await send(c, s, "不同内容", client_msg_id="same")


@pytest.mark.asyncio
async def test_cross_user_session_is_not_disclosed():
    c, _, s = await setup()
    with pytest.raises(ResourceNotFound):
        await c.orchestrator.handle_message(TurnRequest(user_id="other", task_id=s.id, message="继续"))


@pytest.mark.asyncio
async def test_task_write_uses_business_receipt_and_followup():
    async def callback(rt):
        return await rt.action(action("task.set_done", {"task_id": "t1", "done": True}))
    c, engine, s = await setup(callback)
    await c.asset_service.save_action_plan("u1", plan())
    r = await send(c, s)
    assert engine.receipts[-1]["executed"]
    assert (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].done
    assert r.messages[-1].text == engine.text
    assert any(m.role == "system" for m in r.messages)


@pytest.mark.asyncio
async def test_missing_evidence_becomes_pending_not_a_write():
    async def callback(rt):
        return await rt.action(action("task.set_done", {"task_id": "t1", "done": True}, evidence="不是本轮原话"))
    c, engine, s = await setup(callback)
    await c.asset_service.save_action_plan("u1", plan())
    r = await send(c, s)
    assert engine.receipts[-1]["state"] == "proposed"
    assert not (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].done
    assert r.guide.options


@pytest.mark.asyncio
async def test_pending_survives_intervening_question_and_approves_exact_payload():
    async def propose(rt):
        return await rt.action(action("task.set_done", {"task_id": "t1", "done": True}, authorization="proposal"))
    c, engine, s = await setup(propose)
    await c.asset_service.save_action_plan("u1", plan())
    r = await send(c, s)
    option = r.guide.options[0]
    engine.callback = None
    await send(c, s, "先解释一下")
    approved = await send(c, s, "确认执行", option_id=option.option_id, option_value=option.value)
    assert (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].done
    assert any("已更新任务" in m.text for m in approved.messages)


@pytest.mark.asyncio
async def test_version_conflict_invalidates_proposal():
    async def propose(rt):
        return await rt.action(action("task.set_done", {"task_id": "t1", "done": True}, authorization="proposal"))
    c, engine, s = await setup(propose)
    await c.asset_service.save_action_plan("u1", plan())
    r = await send(c, s)
    await c.asset_service.save_action_plan("u1", plan("任务已变"))
    engine.callback = None
    await send(c, s, "确认", option_id=r.guide.options[0].option_id)
    assert not (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].done


@pytest.mark.asyncio
async def test_generated_plan_does_not_replace_existing_or_write_calendar():
    async def create(rt):
        return await rt.action(action("plan.save", plan("新草稿任务").model_dump(mode="json")))
    c, engine, s = await setup(create)
    await c.asset_service.save_action_plan("u1", plan())
    c.orchestrator._functions.write_calendar_node = AsyncMock()
    await send(c, s)
    assert engine.receipts[-1]["receipt"]["draft_saved"]
    assert (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].text == "整理课程笔记"
    c.orchestrator._functions.write_calendar_node.assert_not_called()


@pytest.mark.asyncio
async def test_first_plan_is_saved_and_recoverable():
    async def create(rt):
        return await rt.action(action("plan.save", plan().model_dump(mode="json")))
    c, _, s = await setup(create)
    await send(c, s)
    assert (await c.asset_service.get_action_plan("u1")).phases[0].tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", ["automatic_off", "temporary", "forgotten"])
async def test_automatic_profile_write_respects_controls(setting):
    async def save(rt):
        return await rt.action(action("profile.update", {"key": "major", "value": "人工智能"},
                                     evidence="人工智能", authorization="automatic"))
    c, _, s = await setup(save)
    def set_state(state):
        if setting == "automatic_off":
            state["preferences"] = {"automatic_memory": False}
        elif setting == "temporary":
            state["conversation_settings"] = {s.id: {"temporary": True}}
        else:
            state["conversation_forgotten_keys"] = ["major"]
        return state
    await c.student_state.update("u1", set_state)
    with pytest.raises(InvalidRequest):
        await send(c, s, "人工智能")
    assert not any(f.key == "major" for f in await c.profile_service.get_fields("u1"))


@pytest.mark.asyncio
async def test_profile_update_evidence_and_manual_protection():
    async def save(rt):
        return await rt.action(action("profile.update", {"key": "major", "value": "人工智能"},
                                     evidence="人工智能", authorization="automatic"))
    c, _, s = await setup(save)
    await c.profile_service.correct_field("u1", "major", "数学")
    with pytest.raises(InvalidRequest):
        await send(c, s, "人工智能")
    assert next(f for f in await c.profile_service.get_fields("u1") if f.key == "major").value == "数学"


@pytest.mark.asyncio
async def test_explicit_correction_and_verified_source():
    async def save(rt):
        return await rt.action(action("profile.update", {"key": "major", "value": "人工智能"}, evidence="人工智能"))
    c, engine, s = await setup(save)
    await send(c, s, "我读人工智能")
    assert engine.receipts[-1]["executed"]
    assert next(f for f in await c.profile_service.get_fields("u1") if f.key == "major").value == "人工智能"


@pytest.mark.asyncio
async def test_failed_operation_journal_is_not_retried():
    async def save(rt):
        a = action("task.set_done", {"task_id": "t1", "done": True})
        first = await rt.action(a)
        second = await rt.action(a)
        return first, second
    c, engine, s = await setup(save)
    await c.asset_service.save_action_plan("u1", plan())
    c.orchestrator.task_writer = AsyncMock(side_effect=RuntimeError("synthetic failure"))
    await send(c, s)
    first, second = engine.receipts[-1]
    assert first["state"] == second["state"] == "outcome_unknown"
    assert c.orchestrator.task_writer.await_count == 1


@pytest.mark.asyncio
async def test_cancellation_prevents_next_operation():
    async def cancel(rt):
        await rt.ledger.put_run("u1", rt.request.task_id, rt.request.client_msg_id, cancel_requested=True)
        return await rt.action(action("plan.save", plan().model_dump(mode="json")))
    c, engine, s = await setup(cancel)
    await send(c, s)
    assert engine.receipts[-1]["state"] == "cancelled"
    assert await c.asset_service.get_action_plan("u1") is None


@pytest.mark.asyncio
async def test_progress_events_and_real_receipts():
    async def create(rt):
        return await rt.action(action("plan.save", plan().model_dump(mode="json")))
    c, _, s = await setup(create)
    frames = []
    with progress_channel(frames.append):
        await send(c, s)
    assert [f["type"] for f in frames] == ["run.started", "step.started", "step.completed", "run.completed"]
    assert frames[2]["receipt"]["executed"]


@pytest.mark.asyncio
async def test_ledger_restart_interrupted_request_is_not_reexecuted():
    c, engine, s = await setup()
    from zhiyin_business.services.conversation_ledger import digest
    req = TurnRequest(user_id="u1", task_id=s.id, message="继续", client_msg_id="lost")
    await ConversationLedger(c.student_state).put_run("u1", s.id, "lost", state="running",
        request_hash=digest(req.model_dump(mode="json", exclude={"client_msg_id"})))
    with pytest.raises(InvalidRequest):
        await c.orchestrator.handle_message(req)
    assert not engine.requests


@pytest.mark.asyncio
async def test_expired_and_foreign_confirmation_never_execute():
    async def propose(rt):
        return await rt.action(action("plan.save", plan().model_dump(mode="json"), authorization="proposal"))
    c, engine, s = await setup(propose)
    r = await send(c, s)
    record = await ConversationLedger(c.student_state).read("u1", s.id)
    a = next(iter(record["actions"].values()))
    a["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    await ConversationLedger(c.student_state).put_action("u1", s.id, a)
    engine.callback = None
    await send(c, s, "确认", option_id=r.guide.options[0].option_id)
    assert await c.asset_service.get_action_plan("u1") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,payload", [("task.set_done", {"task_id": "missing", "done": True}),
    ("profile.update", {"key": "user_id", "value": "other"}), ("plan.save", {"phases": []}),
    ("plan.activate", {"draft_id": "other_session"}), ("direction.select", {"plan_id": "unknown"})])
async def test_invalid_targets_and_payloads_are_rejected(operation, payload):
    async def invalid(rt):
        return await rt.action(action(operation, payload))
    c, _, s = await setup(invalid)
    with pytest.raises(InvalidRequest):
        await send(c, s)


@pytest.mark.asyncio
async def test_concurrent_same_request_has_single_effect():
    c, engine, s = await setup()
    await asyncio.gather(send(c, s, client_msg_id="parallel"), send(c, s, client_msg_id="parallel"))
    assert len(engine.requests) == 1


@pytest.mark.asyncio
async def test_undo_unactivated_draft_does_not_create_an_active_version():
    async def save(rt):
        return await rt.action(action("plan.save", plan("草稿任务").model_dump(mode="json")))
    c, engine, s = await setup(save)
    await c.asset_service.save_action_plan("u1", plan())
    await send(c, s)
    draft_id = engine.receipts[-1]["action_id"]
    from zhiyin_kernel.enums import AssetType
    versions = await c.asset_service.list_versions("u1", AssetType.ACTION_PLAN)
    async def undo(rt):
        return await rt.action(action("action.undo", {"target_id": draft_id}, authorization="proposal"))
    engine.callback = undo
    proposed = await send(c, s)
    engine.callback = None
    await send(c, s, "确认撤回草稿", option_id=proposed.guide.options[0].option_id)
    assert len(await c.asset_service.list_versions("u1", AssetType.ACTION_PLAN)) == len(versions)
    assert (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].text == "整理课程笔记"
    record = await ConversationLedger(c.student_state).read("u1", s.id)
    assert record["actions"][draft_id]["state"] == "reverted"


@pytest.mark.asyncio
async def test_failed_generation_retains_actual_write_receipt_and_is_not_retried():
    async def write_then_fail(rt):
        await rt.action(action("plan.save", plan().model_dump(mode="json")))
        raise RuntimeError("synthetic generation failure after write")
    c, engine, s = await setup(write_then_fail)
    with pytest.raises(RuntimeError):
        await send(c, s, client_msg_id="write_then_fail")
    record = await ConversationLedger(c.student_state).read("u1", s.id)
    assert record["runs"]["write_then_fail"]["state"] == "failed"
    assert next(iter(record["actions"].values()))["receipt"]["active_changed"]
    with pytest.raises(InvalidRequest):
        await send(c, s, client_msg_id="write_then_fail")
    assert len(engine.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("assertion", ["negation", "quotation", "hypothesis", "refusal"])
async def test_automatic_memory_refuses_non_affirmative_assertions(assertion):
    async def wrong_fact(rt):
        return await rt.action({"operation": "profile.update", "authorization": "automatic",
            "evidence": "人工智能", "payload": {"key": "major", "value": "人工智能", "assertion_type": assertion}})
    c, _, s = await setup(wrong_fact)
    with pytest.raises(InvalidRequest):
        await send(c, s, "引用：人工智能")
    assert not await c.profile_service.get_fields("u1")


@pytest.mark.asyncio
async def test_progress_is_durable_without_including_partial_model_text():
    from zhiyin_kernel.streaming import emit_progress
    async def progress(rt):
        emit_progress({"type": "step.started", "step_id": "read-plan", "note": "正在读取计划"})
        emit_progress({"type": "message.delta", "text": "不进入状态日志的草稿正文"})
        emit_progress({"type": "step.completed", "step_id": "read-plan", "note": "已读取计划"})
    c, _, s = await setup(progress)
    await send(c, s, client_msg_id="events")
    run = (await ConversationLedger(c.student_state).read("u1", s.id))["runs"]["events"]
    assert any(e.get("note") == "已读取计划" for e in run["events"])
    assert all(e["type"] != "message.delta" for e in run["events"])


@pytest.mark.asyncio
async def test_calendar_write_requires_concrete_confirmation_and_delete_has_own_confirmation():
    async def propose(rt):
        return await rt.action(action("calendar.write", {"title": "复习高数", "due_at": "2026-11-01T19:00:00+08:00"}))
    c, engine, s = await setup(propose)
    pending = await send(c, s)
    assert await c.function_service.list_calendar_nodes("u1") == []
    engine.callback = None
    await send(c, s, "确认这个时间", option_id=pending.guide.options[0].option_id)
    nodes = await c.function_service.list_calendar_nodes("u1")
    assert len(nodes) == 1 and nodes[0].title == "复习高数" and nodes[0].user_id == "u1"
    async def delete(rt):
        return await rt.action(action("calendar.delete", {"node_id": nodes[0].node_id}))
    engine.callback = delete
    pending = await send(c, s)
    assert len(await c.function_service.list_calendar_nodes("u1")) == 1
    engine.callback = None
    await send(c, s, "确认删除这一条", option_id=pending.guide.options[0].option_id)
    assert await c.function_service.list_calendar_nodes("u1") == []


@pytest.mark.asyncio
async def test_history_tool_is_account_bound_and_excludes_temporary_cross_session_reads():
    import json
    from agno.run import RunContext
    from zhiyin_boot.module_platform import product_tools
    c, engine, s = await setup()
    await send(c, s, "这是一条本账号的旧消息")
    other = await c.orchestrator.enter_task("other", "free_chat")
    temporary = await c.sessions.create(s.model_copy(update={"id": "temporary-source"}))
    def temporary_setting(state):
        state["conversation_settings"] = {temporary.id: {"temporary": True}}
        return state
    await c.student_state.update("u1", temporary_setting)
    tool = next(t.handler for m in product_tools(c) for t in m.tools if t.name == "workspace.read")
    async def history(rt):
        ctx = RunContext(run_id="history-test", session_id=s.id, user_id="u1")
        own = json.loads(await tool(ctx, "history", s.id))
        assert any("旧消息" in m["text"] for m in own["messages"])
        with pytest.raises(InvalidRequest):
            await tool(ctx, "history", other.id)
        with pytest.raises(InvalidRequest):
            await tool(ctx, "history", temporary.id)
        return own
    engine.callback = history
    await send(c, s)


@pytest.mark.asyncio
async def test_user_deleting_session_cancels_future_tools_then_removes_run_and_history():
    entered, release = asyncio.Event(), asyncio.Event()
    async def pause(rt):
        entered.set()
        await release.wait()
        return await rt.action(action("plan.save", plan().model_dump(mode="json")))
    c, engine, s = await setup(pause)
    running = asyncio.create_task(send(c, s))
    await entered.wait()
    deleting = asyncio.create_task(c.facade.delete_session("u1", s.id))
    for _ in range(100):
        record = await ConversationLedger(c.student_state).read("u1", s.id)
        if record.get("delete_requested"):
            break
        await asyncio.sleep(0)
    assert record.get("delete_requested")
    release.set()
    await asyncio.gather(running, deleting)
    assert engine.receipts[-1]["state"] == "cancelled"
    assert await c.sessions.get(s.id) is None
    assert not (await ConversationLedger(c.student_state).read("u1", s.id))["runs"]
    assert not await c.memory_service.list_turns("u1", s.id)


@pytest.mark.asyncio
async def test_revising_pending_proposal_invalidates_its_old_button():
    async def propose(rt):
        return await rt.action(action("plan.save", plan("每周三次").model_dump(mode="json"), authorization="proposal"))
    c, engine, s = await setup(propose)
    old = await send(c, s)
    old_id = engine.receipts[-1]["action_id"]
    async def revise(rt):
        return await rt.action(action("plan.save", plan("每周一次").model_dump(mode="json"),
            authorization="proposal", supersedes_action_id=old_id))
    engine.callback = revise
    await send(c, s)
    engine.callback = None
    await send(c, s, "确认旧方案", option_id=old.guide.options[0].option_id)
    assert await c.asset_service.get_action_plan("u1") is None
    record = await ConversationLedger(c.student_state).read("u1", s.id)
    assert record["actions"][old_id]["state"] == "superseded"


@pytest.mark.asyncio
async def test_long_context_summary_keeps_sources_and_cannot_supply_current_authorization():
    c, engine, s = await setup()
    for index in range(45):
        await c.memory_service.record_turn("u1", s.id, role="user" if index % 2 == 0 else "agent",
            text=f"第{index}条历史原文", loop_stage=s.loop_stage, client_msg_id=f"old-{index}")
    class ContextModel(Model):
        supports_semantic_context = True
        async def invoke(self, request):
            if request.prompt_code == "conversation.context":
                messages = request.prompt_vars["messages"]
                assert not request.use_tools
                return AgentResult(agent_id=request.agent_id, valid=True, structured={"items": [
                    {"kind": "decision", "text": "过去讨论过一项选择", "source_ids": [messages[0]["id"]]},
                    {"kind": "fact", "text": "伪造来源不得保留", "source_ids": ["foreign-source"]}]})
            return await super().invoke(request)
    model = ContextModel()
    c.orchestrator._agent_engine = model
    await send(c, s, "现在先聊别的")
    context = model.requests[-1].prompt_vars["earlier_context"]
    assert not context["trusted_instruction"] and len(context["items"]) == 1
    assert context["items"][0]["kind"] == "decision"
    assert await c.asset_service.get_action_plan("u1") is None
    record = await ConversationLedger(c.student_state).read("u1", s.id)
    assert record["context_summary"]["items"] == context["items"]


@pytest.mark.asyncio
async def test_memory_reset_invalidates_old_summary_even_with_little_recent_history():
    from zhiyin_business.services.conversation_ledger import utcnow
    c, engine, s = await setup()
    await ConversationLedger(c.student_state).change("u1", s.id, lambda r: r.update(context_summary={
        "items": [{"text": "删除过的事实", "kind": "fact", "source_ids": ["old"]}], "reset_at": None}))
    await c.student_state.update("u1", lambda state: {**state, "conversation_memory_reset_at": utcnow()})
    await send(c, s)
    assert engine.requests[-1].prompt_vars["earlier_context"] == {}


@pytest.mark.asyncio
async def test_course_question_cannot_become_a_saved_academic_timetable():
    async def extract(rt):
        return await rt.action(action("profile.update", {"key": "courses", "value": "高等数学"},
            evidence="高等数学", authorization="automatic"))
    c, _, s = await setup(extract)
    with pytest.raises(InvalidRequest):
        await send(c, s, "想学好高等数学")
    assert not any(f.key == "courses" for f in await c.profile_service.get_fields("u1"))


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_kev_is_advisory_and_its_failure_does_not_block_the_reply(fails):
    import json
    from types import SimpleNamespace
    from agno.run import RunContext
    from zhiyin_boot.module_platform import product_tools
    from zhiyin_data_sdk.gateways.decision import DecisionResult
    c, engine, s = await setup()
    c.decision = SimpleNamespace(decide=AsyncMock(side_effect=TimeoutError() if fails else None,
        return_value=DecisionResult(model="synthetic-kev", answers={})))
    c.registry_service.get_decision_routing_policy = AsyncMock(return_value={"mode": "enforce",
        "instructions": "判断当前意图", "criteria": {"chat": "普通咨询"}})
    tool = next(t.handler for m in product_tools(c) for t in m.tools if t.name == "workspace.classify")
    async def classify(rt):
        result = json.loads(await tool(RunContext(run_id="kev-test", session_id=s.id, user_id="u1"), "判断当前业务意图"))
        assert (result.get("available") is False) if fails else result["advisory_only"]
        return result
    engine.callback = classify
    response = await send(c, s)
    assert response.messages[-1].text == engine.text
    assert await c.asset_service.get_action_plan("u1") is None


@pytest.mark.asyncio
async def test_json_object_order_cannot_select_the_wrong_latest_run():
    c, _, s = await setup()
    ledger = ConversationLedger(c.student_state)
    def unordered(record):
        record["runs"] = {"z-old": {"created_at": "2026-10-01T00:00:00+00:00"},
                          "a-new": {"created_at": "2026-10-19T00:00:00+00:00"}}
        record["actions"] = {"z-old": {"created_at": "2026-10-01T00:00:00+00:00"},
                             "a-new": {"created_at": "2026-10-19T00:00:00+00:00"}}
    await ledger.change("u1", s.id, unordered)
    record = await ledger.read("u1", s.id)
    assert list(record["runs"])[-1] == list(record["actions"])[-1] == "a-new"


@pytest.mark.asyncio
async def test_compacted_request_replays_durable_reply_without_new_model_or_writes():
    c, engine, s = await setup()
    first = await send(c, s, "第一条", client_msg_id="archive-me")
    for i in range(34):
        await send(c, s, f"第{i}条", client_msg_id=f"later-{i}")
    record = await ConversationLedger(c.student_state).read("u1", s.id)
    assert record["runs"]["archive-me"]["archived"]
    assert sum(bool(r.get("result")) for r in record["runs"].values()) <= 32
    calls = len(engine.requests)
    replay = await send(c, s, "第一条", client_msg_id="archive-me")
    assert replay.model_dump() == first.model_dump() and len(engine.requests) == calls


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", [False, True])
async def test_exact_current_task_title_is_resolved_only_when_unique(duplicate):
    async def mark(rt):
        return await rt.action(action("task.set_done", {"task_text": "整理课程笔记", "done": True}, evidence="整理课程笔记"))
    c, engine, s = await setup(mark)
    p = plan()
    if duplicate:
        p.phases[0].tasks.append(p.phases[0].tasks[0].model_copy(update={"id": "t2"}))
    await c.asset_service.save_action_plan("u1", p)
    if duplicate:
        with pytest.raises(InvalidRequest):
            await send(c, s, "把整理课程笔记标记完成")
        assert not any(t.done for p in (await c.asset_service.get_action_plan("u1")).phases for t in p.tasks)
    else:
        await send(c, s, "把整理课程笔记标记完成")
        assert engine.receipts[-1]["executed"]
        assert (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0].done


@pytest.mark.asyncio
async def test_profile_late_concurrent_edit_cannot_be_overwritten_after_snapshot_check():
    from zhiyin_kernel.blackboard import ProfileField
    from zhiyin_kernel.enums import ProfileSource
    async def change(rt):
        return await rt.action(action("profile.update", {"key": "major", "value": "人工智能"}, evidence="人工智能"))
    c, engine, s = await setup(change)
    await c.profile_service.correct_field("u1", "major", "数学")
    original = c.orchestrator._profiles.get_fields
    injected = False
    async def racing_read(user, *args, **kwargs):
        nonlocal injected
        if not injected:
            injected = True
            await c.profiles.upsert_field(user, ProfileField(key="major", value="物理", confidence=1,
                source=ProfileSource.USER_EDIT, updated_at=datetime.now(timezone.utc)))
        return await original(user, *args, **kwargs)
    c.orchestrator._profiles.get_fields = racing_read
    await send(c, s, "把专业改成人工智能")
    assert next(f for f in await original("u1") if f.key == "major").value == "物理"
    assert not engine.receipts[-1]["executed"]


@pytest.mark.asyncio
async def test_delete_field_cas_preserves_a_later_value():
    from zhiyin_kernel.errors import DuplicateResource
    c, _, _ = await setup()
    await c.profile_service.correct_field("u1", "major", "数学")
    old = next(f for f in await c.profile_service.get_fields("u1") if f.key == "major")
    await c.profile_service.correct_field("u1", "major", "物理")
    with pytest.raises(DuplicateResource):
        await c.profile_service.drop_field("u1", "major", check_version=True, expected_updated_at=old.updated_at)
    assert next(f for f in await c.profile_service.get_fields("u1") if f.key == "major").value == "物理"


@pytest.mark.asyncio
async def test_user_answer_is_logged_once_and_unlocks_real_first_answer_achievement():
    from zhiyin_kernel.enums import BehaviorEventType
    c, _, s = await setup()
    await send(c, s, "先聊聊", client_msg_id="answer-once")
    await send(c, s, "先聊聊", client_msg_id="answer-once")
    events = await c.behavior_service.recent("u1", event_types=[BehaviorEventType.ANSWER])
    assert len(events) == 1 and events[0].payload["session_id"] == s.id
    assert "message" not in events[0].payload
    achievements = await c.function_service.list_achievements("u1")
    assert next(a for a in achievements if a.badge_key == "first_answer").unlocked


@pytest.mark.asyncio
async def test_direction_approval_keeps_decision_event_and_asset_review_chain():
    from zhiyin_kernel.assets import DirectionPlan
    from zhiyin_kernel.enums import PlanRole, BehaviorEventType, AssetType
    async def propose(rt):
        return await rt.action(action("direction.select", {"plan_id": "d1"}, authorization="proposal"))
    c, engine, s = await setup(propose)
    await c.asset_service.save_action_plan("u1", plan())
    await c.asset_service.save_direction_plans("u1", [DirectionPlan(id="d1", role=PlanRole.MAIN,
        name="数据分析", target_desc="探索数据分析方向", fit_reason="用户希望了解", main_risk="还需验证")])
    pending = await send(c, s)
    assert not any(p.selected for p in await c.asset_service.list_direction_plans("u1"))
    engine.callback = None
    await send(c, s, "确认这个方向", option_id=pending.guide.options[0].option_id)
    events = await c.behavior_service.recent("u1", event_types=[BehaviorEventType.DECISION_SELECT])
    assert len(events) == 1 and events[0].payload["plan_id"] == "d1"
    assert (await c.asset_service.get_latest_version("u1", AssetType.ACTION_PLAN)).needs_recompute


@pytest.mark.asyncio
async def test_explicit_patch_and_undo_restore_scheduling_fields_instead_of_inheriting_them():
    async def patch(rt):
        return await rt.action(action("plan.patch", {"updates": [{"task_id": "t1", "fields": {
            "estimated_minutes": 10, "scheduled_at": "2026-11-01T19:00:00+08:00"}}]}, evidence="10分钟"))
    c, engine, s = await setup(patch)
    p = plan()
    p.phases[0].tasks[0].estimated_minutes = 30
    await c.asset_service.save_action_plan("u1", p)
    await send(c, s, "把任务改为10分钟")
    target = engine.receipts[-1]["action_id"]
    changed = (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0]
    assert changed.estimated_minutes == 10 and changed.scheduled_at is not None
    async def undo(rt):
        return await rt.action(action("action.undo", {"target_id": target}, authorization="proposal"))
    engine.callback = undo
    pending = await send(c, s)
    engine.callback = None
    await send(c, s, "确认撤销", option_id=pending.guide.options[0].option_id)
    restored = (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0]
    assert restored.estimated_minutes == 30 and restored.scheduled_at is None


@pytest.mark.asyncio
async def test_generated_plan_cannot_invent_completed_tasks_or_achievements():
    from zhiyin_kernel.enums import BehaviorEventType
    async def generate(rt):
        p = plan()
        p.phases[0].tasks[0].done = True
        p.phases[0].tasks[0].status = "completed"
        p.phases[0].tasks[0].progress = 100
        return await rt.action(action("plan.save", p.model_dump(mode="json")))
    c, _, s = await setup(generate)
    await send(c, s)
    task = (await c.asset_service.get_action_plan("u1")).phases[0].tasks[0]
    assert not task.done and task.status == "pending" and task.progress == 0
    assert not await c.behavior_service.recent("u1", event_types=[BehaviorEventType.TASK_DONE])


@pytest.mark.asyncio
async def test_calendar_commit_invalidates_only_the_current_users_day_advice():
    async def propose(rt):
        return await rt.action(action("calendar.write", {"title": "复习", "due_at": "2026-11-01T19:00:00+08:00"}))
    c, engine, s = await setup(propose)
    for user in ("u1", "other"):
        await c.ai_task_results.put(user, "day.advice.test", {"data": "旧建议"})
    pending = await send(c, s)
    assert await c.ai_task_results.get("u1", "day.advice.test")
    engine.callback = None
    await send(c, s, "确认", option_id=pending.guide.options[0].option_id)
    assert await c.ai_task_results.get("u1", "day.advice.test") is None
    assert await c.ai_task_results.get("other", "day.advice.test") is not None
