"""Contract and permission tests; PostgreSQL/restart/browser acceptance is separate."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import create_app
from zhiyin_business.services.modules import ModulePlatform
from zhiyin_kernel.enums import UserRole
from zhiyin_kernel.errors import AccessDenied, DuplicateResource, InvalidRequest
from zhiyin_kernel.modules import ModulePolicy
from zhiyin_modules import discover, inspect_modules

ROOT = Path(__file__).resolve().parents[1]


class Repository:
    def __init__(self):
        self.policies = {}
        self.records = []

    async def policy(self, mid):
        return copy.deepcopy(self.policies.get(mid, {}))

    async def save_policy(self, mid, policy, actor):
        if policy["revision"] != self.policies.get(mid, {}).get("revision", 0):
            raise DuplicateResource("stale")
        self.policies[mid] = {**policy, "revision": policy["revision"] + 1}
        return self.policies[mid]

    async def record_check(self, actor, report):
        self.records.append(report)
        return report


@pytest.fixture
def platform():
    modules = discover()
    repo = Repository()
    roles = {"admin": UserRole.ADMIN, "dev": UserRole.DEVELOPER, "student": UserRole.STUDENT}
    writes = []

    async def current_user(*, token):
        if token not in roles:
            raise AccessDenied("no login")
        return SimpleNamespace(id=token, role=roles[token])

    async def read(user):
        return {"has_plan": True, "phases": [{"name": user, "tasks": [{"task_id": "t", "text": user, "done": bool(writes)}]}]}

    async def action(user, payload):
        writes.append((user, payload))

    async def agents():
        return [SimpleNamespace(id="coach", name="教练")]

    service = ModulePlatform(modules=modules, repository=repo,
        identity=SimpleNamespace(current_user=current_user), readers={"plan.read": read},
        actions={"plan.task.set_done": action}, revision="a" * 40, environment="workbench",
        inspect=inspect_modules, agents=agents)
    service.test_roles, service.test_writes = roles, writes
    return service


async def enable(service, **overrides):
    return await service.configure("action_progress", ModulePolicy(enabled=True, reads=["plan.read"],
        actions=["plan.task.set_done"], **overrides), "admin")


@pytest.mark.asyncio
async def test_fixture_cannot_write_and_needs_no_live_grant(platform):
    value = await platform.read("action_progress", "dev", mode="fixture", preview=True)
    assert value.data["completed"] == 1
    assert platform.test_writes == []
    with pytest.raises(AccessDenied):
        await platform.read("action_progress", "dev", mode="fixture")


@pytest.mark.asyncio
async def test_disabled_and_revoked_modules_deny_data_and_actions(platform):
    with pytest.raises(AccessDenied):
        await platform.read("action_progress", "student")
    policy = await enable(platform)
    data = await platform.read("action_progress", "student")
    assert data.data["tasks"][0]["text"] == "student"
    await platform.configure("action_progress", policy.model_copy(update={"enabled": False}), "admin")
    with pytest.raises(AccessDenied):
        await platform.perform("action_progress", "student", "plan.task.set_done", {"task_id": "t", "done": True})


@pytest.mark.asyncio
async def test_actions_use_current_user_and_original_business_handler(platform):
    await enable(platform)
    result = await platform.perform("action_progress", "student", "plan.task.set_done", {"task_id": "t", "done": True})
    assert platform.test_writes == [("student", {"task_id": "t", "done": True})]
    assert result.data["completed"] == 1
    with pytest.raises(InvalidRequest):
        await platform.perform("action_progress", "student", "plan.task.set_done", {"user_id": "other"})


@pytest.mark.asyncio
async def test_database_role_revocation_takes_effect_with_same_token(platform):
    assert (await platform.require("admin", admin=True)).id == "admin"
    platform.test_roles["admin"] = UserRole.STUDENT
    with pytest.raises(AccessDenied):
        await platform.require("admin", admin=True)


@pytest.mark.asyncio
async def test_agent_tool_grants_and_disable_are_checked_per_call(platform):
    p = await enable(platform, agents=["coach"])
    assert await platform.tool_names("coach") == ["action_progress.read"]
    assert await platform.tool_names("other") == []
    assert (await platform.tool("action_progress", "student", "coach")).data["total"] == 1
    with pytest.raises(AccessDenied):
        await platform.tool("action_progress", "student", "other")
    await platform.configure("action_progress", p.model_copy(update={"enabled": False}), "admin")
    assert await platform.tool_names("coach") == []
    with pytest.raises(AccessDenied):
        await platform.tool("action_progress", "student", "coach")


@pytest.mark.asyncio
async def test_grant_conflicts_unknown_capabilities_and_unknown_agents(platform):
    await enable(platform)
    with pytest.raises(DuplicateResource):
        await enable(platform)
    with pytest.raises(InvalidRequest):
        await platform.configure("action_progress", ModulePolicy(reads=["all.read"]), "admin")
    with pytest.raises(InvalidRequest):
        await platform.configure("action_progress", ModulePolicy(agents=["nonexistent"]), "admin")


@pytest.mark.parametrize("role,allowed", [("student", False), ("dev", True), ("admin", True)])
def test_developer_api_is_backend_protected(platform, role, allowed):
    app = create_app()
    app.state.module_platform = platform
    with TestClient(app) as client:
        reply = client.get("/api/v1/developer/modules", headers={"Authorization": f"Bearer {role}"})
        assert (reply.status_code == 200) is allowed
        put = client.put("/api/v1/developer/modules/action_progress/policy", headers={"Authorization": f"Bearer {role}"}, json={"enabled": True, "reads": ["plan.read"]})
        assert (put.status_code == 200) is (role == "admin")


@pytest.mark.parametrize("change", ["api_version", "missing_component", "duplicate_id", "cross_boundary", "unknown_read", "wrong_tool", "reserved_tool"])
def test_invalid_module_is_rejected_before_runtime(tmp_path, change):
    source = ROOT / "zhiyin-modules/zhiyin_modules/action_progress"
    folder = tmp_path / "action_progress"
    shutil.copytree(source, folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if change == "api_version":
        manifest["api_version"] = "2"
    elif change == "missing_component":
        (folder / "Card.vue").unlink()
    elif change == "duplicate_id":
        shutil.copytree(folder, tmp_path / "duplicate")
    elif change == "cross_boundary":
        (folder / "backend.py").write_text("import asyncpg\n", encoding="utf-8")
    elif change == "unknown_read":
        manifest["reads"] = ["everyone.read"]
    elif change == "reserved_tool":
        folder.rename(tmp_path / "plan")
        folder = tmp_path / "plan"
        manifest.update(id="plan", tool="plan.read")
    else:
        manifest["tool"] = "profile.read"
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert inspect_modules(tmp_path)["passed"] is False
    with pytest.raises(ValueError):
        discover(tmp_path)


def test_output_validator_rejects_fabricated_progress():
    m = discover()["action_progress"]
    with pytest.raises(ValueError):
        m.validate({"data": {"has_plan": True, "tasks": [], "total": 10, "completed": 8}})


@pytest.mark.asyncio
async def test_all_fixture_checks_have_persisted_result(platform):
    assert (await platform.check("dev"))["passed"]
    assert len(platform.repository.records) == 1


def test_executor_only_accepts_exact_commits_and_redacts_secrets(tmp_path):
    path = ROOT.parents[1] / "deploy/module_executor.py"
    spec = importlib.util.spec_from_file_location("tested_executor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env = tmp_path / "private.env"
    env.write_text("ZHIYIN_EXECUTOR_TOKEN=" + "s" * 40 + "\nPLATFORM_ACCOUNT_PASSWORD=private-password\n", encoding="utf-8")
    instance = module.Executor({"repository": str(tmp_path), "state_directory": str(tmp_path / "state"),
        "compose_file": str(tmp_path / "compose.yml"), "staging_env_file": str(env), "workbench_env_file": str(env)})
    with pytest.raises(ValueError):
        instance.checkout("main; echo injected")
    assert "private-password" not in instance.redact("bad private-password")


def test_template_added_module_needs_no_host_edit(tmp_path):
    source = ROOT / "zhiyin-modules/zhiyin_modules/action_progress"
    target = tmp_path / "independent_card"
    shutil.copytree(source, target)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(id="independent_card", tool="independent_card.read")
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    modules = discover(tmp_path)
    assert list(modules) == ["independent_card"]
    async def read(_):
        return {"has_plan": False, "phases": []}
    from zhiyin_kernel.modules import ModuleContext
    assert asyncio.run(modules["independent_card"].load(ModuleContext("u", "fixture", read)))["empty"]


def test_added_modules_have_distinct_model_callable_names(tmp_path):
    from zhiyin_boot.module_platform import product_tools
    from agno.tools.function import Function
    modules = discover()
    second = modules["action_progress"]
    from dataclasses import replace
    modules["another_progress"] = replace(second, manifest=second.manifest.model_copy(update={
        "id": "another_progress", "tool": "another_progress.read"}))
    container = SimpleNamespace(extra={"modules": modules})
    handlers = [m.tools[0].handler for m in product_tools(container)]
    assert len(handlers) >= 2
    assert len({h.__name__ for h in handlers}) == len(handlers)
    for handler in handlers:
        function = Function.from_callable(handler)
        assert set(function.parameters.get("properties", {})) <= {"input"}, "Model may supply module input, never user identity/context"


@pytest.mark.asyncio
async def test_module_query_cannot_replace_plan_and_cards_survive_history_and_retry():
    from tests.e2e.test_main_path import _container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
    from zhiyin_orchestration.agent import AgentResult
    container = _container()
    user = "module-query"
    await container.asset_service.save_action_plan(user, ActionPlan(id="original", phases=[
        ActionPhase(name="saved", date_range="test", tasks=[ActionTask(id="original-task", text="Original", done=True)])]))
    before = await container.facade.get_action_plan(user)
    payload = {"data": {"has_plan": True, "tasks": [{"task_id": "original-task", "text": "Original", "phase": "saved", "done": True}], "total": 1, "completed": 1}, "sources": ["saved plan"], "empty": False}
    calls = []
    async def invoke(request):
        calls.append(request)
        return AgentResult(agent_id=request.agent_id, valid=True,
            structured={"conclusion": "Generated prose", "phases": [{"name": "wrong replacement", "tasks": [{"text": "Never save this"}]}],
                "guide": {"kind": "task", "text": "Never claim this task was saved"}},
            renderables=[{"kind": "module.action_progress", "title": "进度", "payload": payload}])
    container.orchestrator._agent_engine = SimpleNamespace(invoke=invoke)
    session = await container.orchestrator.enter_task(user, "how_to_act")
    request = TurnRequest(user_id=user, task_id=session.id, message="查看行动计划进度", client_msg_id="module-query-retry")
    first = await container.orchestrator.handle_message(request)
    assert await container.facade.get_action_plan(user) == before
    assert first.asset_versions == [] and first.guide.task is None
    history = await container.facade.list_session_turns(user, session.id)
    from zhiyin_kernel.modules import ModuleResult
    assert history[-1].renderables[0].payload == ModuleResult.model_validate(payload).model_dump()
    again = await container.orchestrator.handle_message(request)
    assert len(calls) == 1
    assert again.messages[0].renderables == first.messages[0].renderables
