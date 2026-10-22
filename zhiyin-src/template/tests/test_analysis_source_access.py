"""Source switches protect model inputs, tool reads, caches and continued turns."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zhiyin_boot import Settings, build_container
from zhiyin_boot.container.services import _lazy_profile_reader, _lazy_plan_reader
from zhiyin_business.contracts.student import Preferences
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_business.services.analysis_access import activate, current_scope, load_scope
from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
from zhiyin_kernel.enums import LoopStage
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_orchestration import AgentResult


@pytest.fixture
def app(tmp_path):
    data = Path(__file__).resolve().parents[1] / "data"
    return build_container(Settings(
        use_remote_llm=True, llm_api_key="sk-test", env="test",
        local_data_dir=str(data), local_registry_dir=str(data / "registry"),
        local_knowledge_dir=str(data / "knowledge"), local_object_dir=str(tmp_path),
    ))


async def seed(app, user="a"):
    for key, value, source in (
        ("major", "ACADEMIC_SENTINEL", "record"),
        ("interest", "LEGACY_DERIVED_SENTINEL", "conversation"),
        ("direction", "MANUAL_SENTINEL", "user_edit"),
    ):
        await app.profile_service.update_field(user, key, value, confidence=1, source=source)
    await app.memory_service.upsert(user, "session", loop_stage=LoopStage.COLLECT,
                                   lead_agent="profile_analyst", summary_delta="LEGACY_SUMMARY_SENTINEL")
    await app.memory_service.record_turn(user, "session", role="agent",
                                        text="LEGACY_TURN_SENTINEL", loop_stage=LoopStage.COLLECT)
    await app.asset_service.save_action_plan(user, ActionPlan(id="old", phases=[
        ActionPhase(date_range="2026-10", name="LEGACY_PLAN_SENTINEL", tasks=[ActionTask(id="task", text="old")]),
    ]))


class Recorder:
    def __init__(self, app):
        self.app, self.requests, self.tools = app, [], []

    async def invoke(self, request):
        self.requests.append(request)
        self.tools.append({
            "profile": await _lazy_profile_reader(self.app)("a"),
            "plan": await _lazy_plan_reader(self.app)("a"),
        })
        return AgentResult(agent_id=request.agent_id, valid=True,
                           structured={"headline": "根据允许的资料生成"}, raw_text="新的回答")


def serialized(value):
    return json.dumps(value, ensure_ascii=False, default=lambda x: x.model_dump(mode="json"))


@pytest.mark.asyncio
@pytest.mark.parametrize("academic,material", [(False, True), (True, False), (False, False)])
async def test_chat_and_tools_exclude_old_derivations_but_keep_allowed_sources(app, academic, material):
    await seed(app)
    await app.student_service.save_preferences("a", Preferences(
        academic_analysis=academic, material_analysis=material,
    ))
    recorder = Recorder(app)
    app.orchestrator._agent_engine = recorder
    app.orchestrator._intent_policy = None
    session = await app.orchestrator.enter_task("a", "free_chat")
    request = TurnRequest(user_id="a", task_id=session.id, message="我想了解自己 CURRENT_SENTINEL",
                          attachment_text="MATERIAL_SENTINEL" if material else "")
    await app.orchestrator.handle_message(request)
    content = serialized(recorder.requests) + serialized(recorder.tools)
    assert "CURRENT_SENTINEL" in content and "MANUAL_SENTINEL" in content
    assert ("ACADEMIC_SENTINEL" in content) is academic
    assert ("MATERIAL_SENTINEL" in content) is material
    for marker in ("LEGACY_DERIVED", "LEGACY_SUMMARY", "LEGACY_TURN", "LEGACY_PLAN"):
        assert marker not in content
    assert current_scope() is None
    # Following turns preserve newly permitted conversation history.
    await app.orchestrator.handle_message(request.model_copy(update={"message": "继续聊 NEXT_SENTINEL"}))
    assert "CURRENT_SENTINEL" in serialized(recorder.requests[-1].history)
    # Normal UI reads still show original data; filtering has not erased it.
    assert "LEGACY_DERIVED" in serialized(await app.profile_service.get("a"))
    assert "LEGACY_SUMMARY" in serialized(await app.memory_service.list_by_user("a"))


@pytest.mark.asyncio
async def test_attachment_rejected_only_when_disabled_before_model_call(app):
    await app.student_service.save_preferences("a", Preferences(material_analysis=False))
    recorder = Recorder(app)
    app.orchestrator._agent_engine = recorder
    with pytest.raises(InvalidRequest, match="移除附件"):
        await app.orchestrator.handle_message(TurnRequest(
            user_id="a", task_id="s", message="读取材料", attachment_text="SECRET"))
    assert not recorder.requests
    assert current_scope() is None


@pytest.mark.asyncio
async def test_new_profile_provenance_survives_reload_and_cannot_forge_manual_source(app):
    await app.student_service.save_preferences("a", Preferences(academic_analysis=False))
    with activate(await load_scope(app.student_state, "a")):
        saved = await app.profile_service.update_field("a", "interest", "MATERIAL_DERIVED",
                                                       confidence=1, source="user_edit")
        assert saved.source.value == "conversation"
    with activate(await load_scope(app.student_state, "a")):
        assert "MATERIAL_DERIVED" in serialized(await app.profile_service.get("a"))
    await app.student_service.save_preferences("a", Preferences(material_analysis=False))
    with activate(await load_scope(app.student_state, "a")):
        assert "MATERIAL_DERIVED" not in serialized(await app.profile_service.get("a"))
    assert "MATERIAL_DERIVED" in serialized(await app.profile_service.get("a"))


@pytest.mark.asyncio
async def test_task_cache_is_partitioned_and_stream_does_not_leak_scope(app):
    await seed(app)
    recorder = Recorder(app)
    app.ai_task_service._engine = recorder

    async def run():
        frames = []
        async for frame in app.ai_task_service.stream("a", "brief.today"):
            assert current_scope() is None
            frames.append(frame)
        return frames[-1]["result"]

    assert not (await run()).meta.cached
    assert (await run()).meta.cached
    assert len(recorder.requests) == 1
    # Change directly in storage: key isolation must work even without invalidation.
    await app.student_state.update("a", lambda s: {**s, "preferences": {
        "academic_analysis": False, "material_analysis": True}})
    assert not (await run()).meta.cached
    assert len(recorder.requests) == 2
    assert "ACADEMIC_SENTINEL" not in serialized(recorder.requests[-1])
    assert "MANUAL_SENTINEL" in serialized(recorder.requests[-1])
    assert (await run()).meta.cached


@pytest.mark.asyncio
async def test_concurrent_accounts_and_exception_cleanup(app):
    await seed(app, "a")
    await seed(app, "b")
    await app.student_service.save_preferences("a", Preferences(academic_analysis=False))

    async def read(user):
        with activate(await load_scope(app.student_state, user)):
            await asyncio.sleep(0)
            value = serialized(await app.profile_service.get(user))
            if user == "a":
                with pytest.raises(InvalidRequest):
                    await app.profile_service.get("b")
            return value

    a, b = await asyncio.gather(read("a"), read("b"))
    assert "ACADEMIC_SENTINEL" not in a and "ACADEMIC_SENTINEL" in b
    assert current_scope() is None
    with pytest.raises(RuntimeError):
        with activate(await load_scope(app.student_state, "a")):
            raise RuntimeError("failed generation")
    assert current_scope() is None


@pytest.mark.asyncio
async def test_new_asset_is_reusable_without_marking_inherited_legacy_text_clean(app):
    await app.student_service.save_preferences("a", Preferences(academic_analysis=False))
    plan = ActionPlan(id="new", phases=[ActionPhase(date_range="2026-10", name="新阶段", tasks=[ActionTask(text="新任务")])])
    with activate(await load_scope(app.student_state, "a")):
        await app.asset_service.save_action_plan("a", plan)
    with activate(await load_scope(app.student_state, "a")):
        assert await app.asset_service.get_action_plan("a") is not None
    await app.student_service.save_preferences("a", Preferences(material_analysis=False))
    with activate(await load_scope(app.student_state, "a")):
        assert await app.asset_service.get_action_plan("a") is None
        changed = plan.model_copy(update={"phases": [plan.phases[0].model_copy(update={"tag": "重新规划"})]})
        await app.asset_service.save_action_plan("a", changed)
        assert await app.asset_service.get_action_plan("a") is None


@pytest.mark.asyncio
async def test_school_snapshot_filter_and_public_intel_cache_boundary(app):
    from zhiyin_data_sdk.gateways.academic import AcademicSnapshot, CourseEntry
    await app.academic_records.upsert("a", AcademicSnapshot(courses=[CourseEntry(name="数据库")]))
    await app.student_service.save_preferences("a", Preferences(academic_analysis=False))
    with activate(await load_scope(app.student_state, "a")):
        assert await app.academic_service.get("a") is None
    await app.student_service.save_preferences("a", Preferences(material_analysis=False))
    with activate(await load_scope(app.student_state, "a")):
        assert (await app.academic_service.get("a")).courses[0].name == "数据库"
        from zhiyin_business.services.analysis_access import guarded
        original = SimpleNamespace(fetch_external_intel=AsyncMock(return_value=[]))
        await guarded(original, "function").fetch_external_intel("a", topic="后端开发")
        original.fetch_external_intel.assert_awaited_once_with(None, topic="后端开发")


@pytest.mark.asyncio
async def test_module_tool_reads_filtered_plan_without_disabling_builtin_module(app):
    from agno.run import RunContext
    from zhiyin_boot.module_platform import definitions, product_tools

    await seed(app)
    await app.student_service.save_preferences("a", Preferences(academic_analysis=False))
    definition = definitions(app)["action_progress"]

    async def read(*args):
        plan = await app.facade.get_action_plan("a")
        return SimpleNamespace(model_dump=lambda: {"data": plan.model_dump(mode="json")})

    app.extra["module_platform"] = SimpleNamespace(
        definition=lambda mid: definition, tool=read,
    )
    handler = next(m.tools[0].handler for m in product_tools(app) if m.name == "action_progress")
    context = RunContext(run_id="r", session_id="s", user_id="a", dependencies={"module_agent_id": "coach"})
    with activate(await load_scope(app.student_state, "a")):
        result = json.loads(await handler(context))
    assert result["data"]["has_plan"] is False
    assert "LEGACY_PLAN" not in serialized(result)
    assert context.dependencies["module_results"]


@pytest.mark.asyncio
async def test_cancelled_stream_restores_context_before_returning_progress(app):
    await app.student_service.save_preferences("a", Preferences(academic_analysis=False))
    app.ai_task_service._progress_notes = AsyncMock(return_value=["读取允许的资料"])
    iterator = app.ai_task_service.stream("a", "brief.today")
    assert "pct" in await anext(iterator)
    assert current_scope() is None
    await iterator.aclose()
    assert current_scope() is None
