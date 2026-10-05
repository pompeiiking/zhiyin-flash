"""Application/skill boundaries, ancestry switches, and structured tool results."""
import asyncio
import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import create_app
from zhiyin_business.services.modules import ModulePlatform
from zhiyin_kernel.enums import UserRole
from zhiyin_kernel.errors import AccessDenied, InvalidRequest
from zhiyin_kernel.modules import ModuleManifest, ModulePolicy
from zhiyin_modules import discover, inspect_modules

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "zhiyin-modules/zhiyin_modules"
PARENT = "action_progress"
SKILL = "plan_progress_skill"


def manifest_data(module_id=PARENT):
    return json.loads((MODULES / module_id / "manifest.json").read_text(encoding="utf-8"))


def copy_module(root, module_id, *, source=PARENT, **changes):
    destination = root / module_id
    shutil.copytree(MODULES / source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest = manifest_data(source)
    manifest.update(id=module_id, parent_id=None, dependencies={})
    if manifest.get("tool"):
        manifest["tool"] = f"{module_id}.read"
    manifest.update(changes)
    (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return destination


@pytest.mark.parametrize("module_id,kind", [(PARENT, "hybrid"), ("achievements", "application")])
def test_legacy_declarations_infer_compatible_kind(module_id, kind):
    data = manifest_data(module_id)
    data.pop("kind")
    assert ModuleManifest.model_validate(data).kind == kind


@pytest.mark.parametrize("changes", [
    {"kind": "application", "tool": "action_progress.read"},
    {"kind": "application", "tool": None, "card": None},
    {"kind": "hybrid", "tool": None},
    {"kind": "hybrid", "card": None},
    {"kind": "tool", "card": "Card.vue", "detail": None},
    {"kind": "tool", "card": None, "detail": "Detail.vue"},
    {"kind": "tool", "card": None, "detail": None, "tool": None},
    {"kind": "unknown"},
])
def test_incompatible_entrypoints_are_rejected(changes):
    with pytest.raises(ValueError):
        ModuleManifest.model_validate({**manifest_data(), **changes})


def test_pure_skill_is_discovered_without_any_vue_file(tmp_path):
    folder = copy_module(tmp_path, "standalone_skill", source=SKILL)
    assert not list(folder.glob("*.vue"))
    modules = discover(tmp_path)
    manifest = modules["standalone_skill"].manifest
    assert manifest.kind == "tool" and manifest.card is None and manifest.detail is None
    assert manifest.conversation is None and manifest.actions == []


def test_skill_can_explicitly_provide_a_conversation_view(tmp_path):
    folder = copy_module(tmp_path, "visual_skill", source=SKILL, conversation="Card.vue")
    shutil.copyfile(MODULES / PARENT / "Card.vue", folder / "Card.vue")
    assert discover(tmp_path)["visual_skill"].manifest.card is None
    (folder / "Card.vue").unlink()
    assert not inspect_modules(tmp_path)["passed"]


@pytest.mark.parametrize("case", ["missing", "skill_parent", "self", "cycle", "deep_cycle"])
def test_invalid_hierarchy_is_rejected_before_runtime(tmp_path, case):
    if case == "missing":
        copy_module(tmp_path, "child", source=SKILL, parent_id="missing")
    elif case == "skill_parent":
        copy_module(tmp_path, "parent_skill", source=SKILL)
        copy_module(tmp_path, "child", source=SKILL, parent_id="parent_skill")
    elif case == "self":
        copy_module(tmp_path, "parent", parent_id="parent")
    else:
        copy_module(tmp_path, "first", parent_id="second")
        copy_module(tmp_path, "second", parent_id="first" if case == "cycle" else "third")
        if case == "deep_cycle":
            copy_module(tmp_path, "third", parent_id="first")
    assert not inspect_modules(tmp_path)["passed"]
    with pytest.raises(ValueError):
        discover(tmp_path)


@pytest.fixture
def platform():
    class Repository:
        def __init__(self):
            self.policies = {}

        async def policy(self, mid):
            return copy.deepcopy(self.policies.get(mid, {}))

        async def save_policy(self, mid, policy, actor):
            self.policies[mid] = {**policy, "revision": policy["revision"] + 1}
            return self.policies[mid]

    async def current_user(*, token):
        return SimpleNamespace(id=token, role=UserRole.ADMIN if token == "admin" else UserRole.STUDENT)

    async def read(user):
        return {"has_plan": True, "phases": [{"name": "Saved", "tasks": [
            {"task_id": "task", "text": user, "done": True}]}]}

    async def agents():
        return [SimpleNamespace(id="coach", name="教练")]

    return ModulePlatform(modules=discover(), repository=Repository(),
        identity=SimpleNamespace(current_user=current_user), readers={"plan.read": read}, actions={},
        revision="a" * 40, environment="workbench", inspect=inspect_modules, agents=agents)


async def configure(platform, module_id, **changes):
    old = await platform.policy(module_id)
    values = {**old.model_dump(), "enabled": True, "reads": platform.definition(module_id).manifest.reads, **changes}
    return await platform.configure(module_id, ModulePolicy.model_validate(values), "admin")


@pytest.mark.asyncio
async def test_new_skill_starts_disabled_and_without_inherited_grants(platform):
    await configure(platform, PARENT, agents=["coach"], actions=["plan.task.set_done"])
    child = await platform.policy(SKILL)
    assert child == ModulePolicy()
    assert f"{SKILL}.read" not in await platform.tool_names("coach")
    with pytest.raises(AccessDenied):
        await platform.tool(SKILL, "student", "coach")
    with pytest.raises(InvalidRequest):
        await platform.configure(SKILL, ModulePolicy(enabled=True), "admin")
    await configure(platform, SKILL)
    with pytest.raises(AccessDenied):
        await platform.tool(SKILL, "student", "coach")
    with pytest.raises(InvalidRequest):
        await configure(platform, SKILL, actions=["plan.task.set_done"])
    await configure(platform, SKILL, agents=["coach"])
    assert (await platform.tool(SKILL, "student", "coach")).data["completed"] == 1


@pytest.mark.asyncio
async def test_disabling_parent_removes_child_tool_and_denies_retained_calls(platform):
    await configure(platform, PARENT)
    await configure(platform, SKILL, agents=["coach"])
    assert f"{SKILL}.read" in await platform.tool_names("coach")
    await configure(platform, PARENT, enabled=False)
    view = {item.manifest.id: item for item in await platform.listing()}[SKILL]
    assert view.policy.enabled and not view.effective_enabled
    assert view.blocked_by == [PARENT]
    assert f"{SKILL}.read" not in await platform.tool_names("coach")
    with pytest.raises(AccessDenied):
        await platform.tool(SKILL, "student", "coach")
    with pytest.raises(AccessDenied):
        await platform.read(SKILL, "student")
    assert (await platform.read(SKILL, "student", mode="fixture", preview=True)).data["total"] == 2
    await configure(platform, PARENT)
    assert f"{SKILL}.read" in await platform.tool_names("coach")


@pytest.mark.asyncio
async def test_all_ancestors_control_enablement_without_appearing_as_self_blocks(platform):
    parent = platform.modules[PARENT]
    platform.modules[PARENT] = replace(parent, manifest=parent.manifest.model_copy(update={"parent_id": "achievements"}))
    await configure(platform, PARENT)
    await configure(platform, SKILL, agents=["coach"])
    view = {item.manifest.id: item for item in await platform.listing()}[SKILL]
    assert view.blocked_by == ["achievements"] and not view.effective_enabled
    await configure(platform, "achievements")
    await configure(platform, SKILL, enabled=False)
    view = {item.manifest.id: item for item in await platform.listing()}[SKILL]
    assert view.blocked_by == [] and not view.effective_enabled


@pytest.mark.asyncio
async def test_parent_revocation_during_data_read_does_not_leak_result(platform):
    await configure(platform, PARENT)
    await configure(platform, SKILL, agents=["coach"])
    reader = platform.readers["plan.read"]

    async def read_and_revoke(user):
        result = await reader(user)
        await configure(platform, PARENT, enabled=False)
        return result

    platform.readers["plan.read"] = read_and_revoke
    with pytest.raises(AccessDenied):
        await platform.tool(SKILL, "student", "coach")


def test_user_home_excludes_pure_skills_but_admin_sees_them(platform):
    asyncio.run(configure(platform, PARENT))
    asyncio.run(configure(platform, SKILL, agents=["coach"]))
    app = create_app()
    app.state.module_platform = platform
    with TestClient(app) as client:
        public = client.get("/api/v1/app/modules", headers={"Authorization": "Bearer student"})
        managed = client.get("/api/v1/developer/modules", headers={"Authorization": "Bearer admin"})
    assert public.status_code == managed.status_code == 200
    assert PARENT in {row["manifest"]["id"] for row in public.json()["data"]}
    assert SKILL not in {row["manifest"]["id"] for row in public.json()["data"]}
    assert SKILL in {row["manifest"]["id"] for row in managed.json()["data"]}


def test_optional_skill_view_is_visible_only_on_conversation_surface(platform):
    skill = platform.modules[SKILL]
    platform.modules[SKILL] = replace(skill, manifest=skill.manifest.model_copy(update={"conversation": "Card.vue"}))
    asyncio.run(configure(platform, PARENT))
    asyncio.run(configure(platform, SKILL, agents=["coach"]))
    app = create_app()
    app.state.module_platform = platform
    headers = {"Authorization": "Bearer student"}
    with TestClient(app) as client:
        home = client.get("/api/v1/app/modules", headers=headers)
        conversation = client.get("/api/v1/app/modules?surface=conversation", headers=headers)
        assert home.status_code == conversation.status_code == 200
        assert SKILL not in {row["manifest"]["id"] for row in home.json()["data"]}
        assert SKILL in {row["manifest"]["id"] for row in conversation.json()["data"]}
        asyncio.run(configure(platform, PARENT, enabled=False))
        stopped = client.get("/api/v1/app/modules?surface=conversation", headers=headers)
        assert stopped.status_code == 200
        assert SKILL not in {row["manifest"]["id"] for row in stopped.json()["data"]}


@pytest.mark.asyncio
async def test_skill_handler_returns_structured_result_without_fabricating_a_card(platform):
    from agno.run import RunContext
    from agno.tools.function import Function
    from zhiyin_boot.module_platform import product_tools

    await configure(platform, PARENT)
    await configure(platform, SKILL, agents=["coach"])
    container = SimpleNamespace(extra={"modules": platform.modules, "module_platform": platform})
    tool = next(module.tools[0] for module in product_tools(container) if module.name == SKILL)
    assert set(Function.from_callable(tool.handler).parameters.get("properties", {})) <= {"input"}
    context = RunContext(run_id="skill-test", user_id="student", session_id="skill-test",
                         dependencies={"module_agent_id": "coach"})
    result = json.loads(await tool.handler(context))
    assert result["data"]["tasks"][0]["text"] == "student"
    assert not context.dependencies.get("renderables")
    assert context.dependencies["module_results"] == [{"module_id": SKILL,
        "title": platform.definition(SKILL).manifest.name, "result": result}]
    await configure(platform, PARENT, enabled=False)
    with pytest.raises(AccessDenied):
        await tool.handler(context)


@pytest.mark.asyncio
async def test_pure_skill_query_uses_verified_summary_and_preserves_plan_history_and_retry():
    from tests.e2e.test_main_path import _container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
    from zhiyin_orchestration.agent import AgentResult

    container = _container()
    user = "pure-skill-query"
    await container.asset_service.save_action_plan(user, ActionPlan(id="saved", phases=[
        ActionPhase(name="saved", date_range="test", tasks=[ActionTask(id="original-task", text="Original", done=True)])]))
    before = await container.facade.get_action_plan(user)
    prose = "你的计划共有 1 项任务，目前已完成 1 项。"
    payload = {"data": {"has_plan": True, "tasks": [
        {"task_id": "original-task", "text": "Original", "phase": "saved", "done": True}],
        "total": 1, "completed": 1, "summary": prose}, "sources": ["saved plan"], "empty": False}
    calls = []
    invented_prose = "我已经替你新增了 100 项任务。"

    async def invoke(request):
        calls.append(request)
        return AgentResult(agent_id=request.agent_id, valid=True, raw_text=invented_prose,
            structured={"conclusion": invented_prose, "phases": [{"name": "wrong", "tasks": [{"text": "Never save this"}]}],
                        "guide": {"kind": "task", "text": "Never claim this task was saved"}},
            module_results=[{"module_id": SKILL, "title": "计划进度查询技能", "result": payload}])

    container.orchestrator._agent_engine = SimpleNamespace(invoke=invoke)
    session = await container.orchestrator.enter_task(user, "how_to_act")
    request = TurnRequest(user_id=user, task_id=session.id, message="查询计划完成情况", client_msg_id="skill-retry")
    first = await container.orchestrator.handle_message(request)
    assert await container.facade.get_action_plan(user) == before
    assert first.asset_versions == [] and first.guide.task is None
    assert first.messages[0].text == prose and first.messages[0].renderables == []
    history = await container.facade.list_session_turns(user, session.id)
    assert history[-1].renderables == []
    repeated = await container.orchestrator.handle_message(request)
    assert len(calls) == 1
    assert repeated.messages[0].text == prose and repeated.messages[0].renderables == []


@pytest.mark.asyncio
async def test_denied_skill_attempt_cannot_save_model_plan_or_claim_success(platform):
    from agno.run import RunContext
    from tests.e2e.test_main_path import _container
    from zhiyin_boot.module_platform import product_tools
    from zhiyin_business.contracts.act import ActOutput
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
    from zhiyin_orchestration.agent import AgentResult

    await configure(platform, PARENT)
    await configure(platform, SKILL, agents=["coach"])
    tool_container = SimpleNamespace(extra={"modules": platform.modules, "module_platform": platform})
    tool = next(module.tools[0] for module in product_tools(tool_container) if module.name == SKILL)
    await configure(platform, PARENT, enabled=False)

    container = _container()
    user = "denied-skill-query"
    await container.asset_service.save_action_plan(user, ActionPlan(id="saved", phases=[
        ActionPhase(name="saved", date_range="test", tasks=[ActionTask(id="original-task", text="Original", done=True)])]))
    before = await container.facade.get_action_plan(user)
    invented_prose = "查询成功，我已经替你保存了新的行动计划。"
    proposed_plan = ActOutput.model_validate({"conclusion": invented_prose,
        "phases": [{"name": "new plan", "date_range": "today", "tasks": [
            {"id": "generated-task", "text": "Never save this", "done": False}]}],
        "guide": {"kind": "task", "text": "Never claim this task was saved",
                  "task": {"task_id": "generated-task", "text": "Never save this"}}}).model_dump(mode="json")
    calls = []

    async def invoke(request):
        calls.append(request)
        context = RunContext(run_id="denied-skill", user_id=user, session_id="denied-skill",
                             dependencies={"module_agent_id": "coach"})
        with pytest.raises(AccessDenied):
            await tool.handler(context)
        assert context.dependencies["module_attempts"] == [SKILL]
        assert not context.dependencies.get("module_results")
        assert not context.dependencies.get("renderables")
        return AgentResult(agent_id=request.agent_id, valid=True, raw_text=invented_prose,
            structured=proposed_plan, module_attempts=context.dependencies["module_attempts"])

    container.orchestrator._agent_engine = SimpleNamespace(invoke=invoke)
    session = await container.orchestrator.enter_task(user, "how_to_act")
    request = TurnRequest(user_id=user, task_id=session.id, message="查询计划完成情况", client_msg_id="denied-skill-retry")
    result = await container.orchestrator.handle_message(request)
    assert await container.facade.get_action_plan(user) == before
    assert result.asset_versions == [] and result.guide.task is None
    assert result.messages[0].renderables == []
    assert result.messages[0].text != invented_prose
    assert result.messages[0].text == "本次技能查询未完成，请确认模块启用状态和调用权限后重试。"
    repeated = await container.orchestrator.handle_message(request)
    assert len(calls) == 1
    assert repeated.messages[0].text == result.messages[0].text
    assert repeated.messages[0].renderables == []


@pytest.mark.parametrize("kind", ["application", "tool", "hybrid"])
def test_cli_creates_valid_entrypoints_and_parent_without_host_edits(tmp_path, monkeypatch, kind):
    spec = importlib.util.spec_from_file_location("classification_cli", ROOT / "scripts/module_cli.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    copy_module(tmp_path, PARENT)
    copy_module(tmp_path, SKILL, source=SKILL)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    folder = cli.create("new_feature", "新功能", "测试开发者", kind, PARENT)
    manifest = discover(tmp_path)["new_feature"].manifest
    assert manifest.kind == kind and manifest.parent_id == PARENT
    if kind == "tool":
        assert not list(folder.glob("*.vue")) and manifest.actions == []
        definition = discover(tmp_path)["new_feature"]

        async def read(capability):
            return definition.fixture()[capability]

        from zhiyin_kernel.modules import ModuleContext
        result = asyncio.run(definition.load(ModuleContext("fixture", "fixture", read)))
        assert result["data"]["summary"] == "你的计划共有 2 项任务，目前已完成 1 项。"
    elif kind == "application":
        assert manifest.tool is None and manifest.conversation is None
    else:
        assert manifest.tool == "new_feature.read" and manifest.card == "Card.vue"


def test_cli_rejects_missing_parent_without_leaving_partial_directory(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("classification_cli", ROOT / "scripts/module_cli.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="父模块不存在"):
        cli.create("new_skill", "新技能", "测试开发者", "tool", "missing")
    assert not (tmp_path / "new_skill").exists()
