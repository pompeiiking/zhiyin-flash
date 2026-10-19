"""Professional capabilities, public explanations and durable focus transitions."""
from unittest.mock import AsyncMock

import pytest

from tests.test_dialogue_runtime import setup, send
from zhiyin_orchestration import AgentResult
from zhiyin_orchestration.impl.dialogue_specialists import specialist_tools
from zhiyin_kernel.streaming import progress_channel


def state():
    return {"lead": "career_advisor", "stage": "collect", "roles": [],
            "methods": {}, "clues": [], "theories": []}


@pytest.mark.asyncio
async def test_professionals_load_distinct_guidance_and_methods_without_writes():
    c, _, _ = await setup()
    s = state()
    load, clues = specialist_tools(c.registry_service, s)
    frames, instructions = [], []
    with progress_channel(frames.append):
        for role, focus in [("profile_analyst", "collect"), ("career_advisor", "decide"),
                            ("path_planner", "act"), ("companion_coach", "review"), ("info_scout", "")]:
            result = await load(role, focus)
            assert result["loaded"]
            instructions.append(result["instructions"])
    assert len(set(instructions)) == 5
    assert s["lead"] == "companion_coach" and s["stage"] == "review"
    assert len(frames) == 5 and all(f["type"] == "role.selected" for f in frames)
    assert await c.asset_service.get_action_plan("u1") is None
    assert not (await clues([], [], ["invented_method"]))["saved"]
    assert not (await clues(["a" * 241], [], []))["saved"]
    method = next(iter(s["methods"]))
    assert (await clues(["先用低成本任务验证时间是否够用"], ["岗位要求还未查证"], [method]))["saved"]
    assert len(s["clues"]) == 2 and s["theories"] == [method]


@pytest.mark.asyncio
async def test_disabled_or_wrong_focus_does_not_impersonate_specialist():
    c, _, _ = await setup()
    s = state()
    load, _ = specialist_tools(c.registry_service, s)
    assert not (await load("path_planner", "decide"))["loaded"]
    assert s["roles"] == [] and s["lead"] == "career_advisor"
    role = await c.registry_service.get_agent("path_planner")
    registry = AsyncMock()
    registry.get_agent.return_value = role.model_copy(update={"status": "disabled"})
    registry.get_prompt.return_value = await c.registry_service.get_prompt("conversation.role.path_planner")
    load, _ = specialist_tools(registry, s)
    assert not (await load("path_planner", "act"))["loaded"]
    assert s["roles"] == []


@pytest.mark.asyncio
async def test_focus_clues_and_role_persist_without_asset_or_approval_side_effects():
    c, engine, session = await setup()
    engine.invoke = AsyncMock(return_value=AgentResult(agent_id="path_planner", valid=True,
        raw_text="先用25分钟整理一页课程笔记。", structured={"dialogue_roles": ["path_planner"],
            "dialogue_stage": "act", "dialogue_clues": ["判断标准：今天能完成的小任务"],
            "dialogue_theories": [{"theory_id": "smart", "name": "SMART", "stage": "act"}]}))
    result = await send(c, session, "帮我规划今天怎么开始", client_msg_id="professional")
    assert result.badge.agent_id == "path_planner" and result.stage.value == "act"
    assert result.messages[-1].clues == ["判断标准：今天能完成的小任务"]
    assert (await c.orchestrator._sessions.get(session.id)).lead_agent == "path_planner"
    assert await c.asset_service.get_action_plan("u1") is None
    assert not result.guide.options
    turns = await c.memory_service.list_turns("u1", session.id, limit=10)
    saved = turns[-1]
    assert saved.agent_id == "path_planner"
    assert saved.metadata["result"]["messages"][-1]["clues"] == result.messages[-1].clues
    replay = await send(c, session, "帮我规划今天怎么开始", client_msg_id="professional")
    assert replay.badge.agent_id == "path_planner" and engine.invoke.await_count == 1


@pytest.mark.asyncio
async def test_incomplete_generation_cannot_commit_new_focus():
    c, engine, session = await setup()
    engine.invoke = AsyncMock(return_value=AgentResult(agent_id="path_planner", valid=False,
        raw_text="先从", structured={"dialogue_roles": ["path_planner"], "dialogue_stage": "act"}))
    result = await send(c, session)
    assert result.stage == session.loop_stage
    assert result.badge.agent_id == session.lead_agent


@pytest.mark.asyncio
async def test_existing_database_gets_missing_professional_prompts_without_overwrite():
    from zhiyin_infrastructure.postgres.registry import PostgresRegistryRepository
    repository = PostgresRegistryRepository(AsyncMock(), "data/registry")
    repository._count_ai = AsyncMock(return_value=1)
    repository._insert_missing_prompt = AsyncMock()
    await repository._ensure_ai_seeded()
    codes = {call.args[0]["code"] for call in repository._insert_missing_prompt.await_args_list}
    assert all("conversation.role." + role in codes for role in [
        "profile_analyst", "career_advisor", "path_planner", "companion_coach", "info_scout"])
    assert "conversation.main" in codes
    assert "role.path_planner.act" not in codes
