"""Input/output contracts, pinned dataflows, authorization and durable receipts."""
import copy
import json
import shutil
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zhiyin_business.services.module_flows import ModuleFlowService
from zhiyin_kernel.errors import AccessDenied, DuplicateResource, InvalidRequest, ResourceNotFound
from zhiyin_kernel.modules import ModuleFlowDraft, ModuleFlowRunRequest, ModuleManifest, ModulePolicy
from tests.test_module_platform import platform as _platform_fixture
from zhiyin_api.app import create_app
from zhiyin_modules import inspect_modules


@pytest.fixture
def platform():
    return _platform_fixture.__wrapped__()


class FlowRepository:
    def __init__(self):
        self.drafts, self.published, self.receipts = {}, {}, {}

    async def get(self, workflow_id, *, published=False):
        if workflow_id not in self.drafts:
            raise ResourceNotFound("missing")
        value = copy.deepcopy(self.drafts[workflow_id])
        if published:
            if value["published_revision"] is None or workflow_id not in self.published:
                raise ResourceNotFound("unpublished")
            value.update(copy.deepcopy(self.published[workflow_id]))
        return value

    async def list(self):
        return copy.deepcopy(list(self.drafts.values()))

    async def runs(self, workflow_id, actor=None):
        return [copy.deepcopy(value["run"]) for (wid, uid, _), value in self.receipts.items()
                if wid == workflow_id and (actor is None or uid == actor)]

    async def save(self, draft, actor):
        current = self.drafts.get(draft["id"], {})
        if draft["expected_revision"] != current.get("revision", 0):
            raise DuplicateResource("stale")
        value = {"id": draft["id"], "name": draft["name"], "owner": current.get("owner", actor),
            "revision": current.get("revision", 0) + 1, "published_revision": current.get("published_revision"),
            "definition": {"input_schema": draft["input_schema"], "nodes": draft["nodes"]}, "updated_at": "test"}
        self.drafts[draft["id"]] = copy.deepcopy(value)
        return value

    async def publish(self, workflow_id, revision, definition, actor):
        value = self.drafts[workflow_id]
        if value["revision"] != revision:
            raise DuplicateResource("stale")
        self.published[workflow_id] = {"revision": revision, "definition": copy.deepcopy(definition)}
        value["published_revision"] = revision
        return copy.deepcopy(value)

    async def begin_run(self, workflow_id, revision, actor, request_id, digest, mode):
        key = (workflow_id, actor, request_id)
        if key in self.receipts:
            existing = self.receipts[key]
            if existing["digest"] != digest:
                raise DuplicateResource("request reused")
            return copy.deepcopy(existing["run"]), False
        run = {"id": str(len(self.receipts)), "workflow_id": workflow_id, "revision": revision, "status": "running",
               "mode": mode, "outputs": {}, "trace": [], "error": "", "action_committed": False}
        self.receipts[key] = {"digest": digest, "run": copy.deepcopy(run)}
        return run, True

    async def unpublish(self, workflow_id, revision, actor):
        value = self.drafts[workflow_id]
        if value["revision"] != revision:
            raise DuplicateResource("stale")
        value["published_revision"] = None
        return copy.deepcopy(value)

    async def update_run(self, run):
        for receipt in self.receipts.values():
            if receipt["run"]["id"] == run["id"]:
                receipt["run"] = copy.deepcopy(run)
        return run


async def enable(platform):
    await platform.configure("action_progress", ModulePolicy(enabled=True, reads=["plan.read"], actions=["plan.task.set_done"]), "admin")


def draft(**changes):
    return ModuleFlowDraft.model_validate({"id": "test_flow", "name": "Data flow", "nodes": [
        {"id": "read", "module_id": "action_progress"}], **changes})


@pytest.mark.parametrize("schema", [{"$ref": "https://example.com/schema"},
    {"properties": {"x": {"$ref": "file:///private"}}}, {"$defs": {"x": {"$dynamicRef": "https://example.com"}}},
    {"type": "wrong"}])
def test_schema_rejects_invalid_or_external_references(schema):
    with pytest.raises(ValidationError):
        ModuleManifest(id="test_module", name="Test", version="1.0.0", owner="test", description="test", input_schema=schema)


@pytest.mark.asyncio
async def test_input_is_delivered_and_full_output_contract_is_checked(platform):
    await enable(platform)
    definition = platform.modules["action_progress"]
    manifest = definition.manifest.model_copy(update={
        "input_schema": {"type": "object", "required": ["label"], "properties": {"label": {"type": "string", "pattern": "^ok", "maxLength": 5}}, "additionalProperties": False},
        "output_schema": {"type": "object", "required": ["label"], "properties": {"label": {"oneOf": [{"const": "ok"}, {"const": "okay"}]}}}})
    async def load(context):
        return {"data": {"label": context.input["label"]}}
    platform.modules["action_progress"] = replace(definition, manifest=manifest, load=load, validate=lambda value: value)
    assert (await platform.invoke("action_progress", "user", {"label": "ok"})).data == {"label": "ok"}
    for value in ({}, {"label": "bad"}, {"label": "oklong"}, {"label": "ok", "user_id": "other"}, {"label": "okbad"}):
        with pytest.raises(InvalidRequest):
            await platform.invoke("action_progress", "user", value)
    with pytest.raises(DuplicateResource):
        await platform.invoke("action_progress", "user", {"label": "ok"}, expected_version="9.0.0")


@pytest.mark.asyncio
async def test_reads_record_real_capability_and_current_user(platform):
    await enable(platform)
    value = await platform.invoke("action_progress", "alice")
    assert value.data["tasks"][0]["text"] == "alice"
    assert value.trace == [{"capability": "plan.read", "operation": "read", "mode": "live", "status": "succeeded"}]
    assert (await platform.invoke("action_progress", "bob")).data["tasks"][0]["text"] == "bob"
    platform.repository.policies["action_progress"]["enabled"] = False
    with pytest.raises(AccessDenied):
        await platform.invoke("action_progress", "alice")


@pytest.mark.asyncio
async def test_draft_concurrency_owner_and_published_snapshot(platform):
    service = ModuleFlowService(platform, FlowRepository())
    await service.save(draft(), "dev")
    with pytest.raises(DuplicateResource):
        await service.save(draft(), "dev")
    with pytest.raises(AccessDenied):
        await service.save(draft(expected_revision=1), "other")
    await service.publish("test_flow", 1, "dev")
    await service.save(draft(expected_revision=1, name="Changed"), "dev")
    assert (await service.repository.get("test_flow"))["revision"] == 2
    assert (await service.repository.get("test_flow", published=True))["revision"] == 1
    with pytest.raises(DuplicateResource):
        await service.publish("test_flow", 1, "dev")


@pytest.mark.parametrize("nodes", [
    [{"id": "same", "module_id": "action_progress"}, {"id": "same", "module_id": "action_progress"}],
    [{"id": "a", "module_id": "action_progress", "bindings": {"x": "missing/data/x"}}],
    [{"id": "a", "module_id": "action_progress", "bindings": {"x": "b/data/x"}}, {"id": "b", "module_id": "action_progress", "bindings": {"x": "a/data/x"}}],
    [{"id": "a", "module_id": "action_progress", "operation": "action", "action": "plan.task.set_done"}, {"id": "b", "module_id": "action_progress", "bindings": {"x": "a/data/x"}}],
])
@pytest.mark.asyncio
async def test_invalid_graph_is_rejected_before_execution(platform, nodes):
    service = ModuleFlowService(platform, FlowRepository())
    with pytest.raises(InvalidRequest):
        await service.save(draft(nodes=nodes), "dev")


@pytest.mark.asyncio
async def test_bound_action_real_readback_and_retries_do_not_write_twice(platform):
    await enable(platform)
    service = ModuleFlowService(platform, FlowRepository())
    value = draft(nodes=[{"id": "progress", "module_id": "action_progress"},
        {"id": "complete", "module_id": "action_progress", "operation": "action", "action": "plan.task.set_done",
         "input": {"done": True}, "bindings": {"task_id": "progress/data/tasks/0/task_id"}}])
    await service.save(value, "dev")
    body = ModuleFlowRunRequest(mode="live", confirm_actions=True, request_id="request_001")
    result = await service.run(value.id, "dev", body)
    assert result["status"] == "succeeded" and result["action_committed"]
    assert result["outputs"]["complete"]["data"]["completed"] == 1
    assert platform.test_writes == [("dev", {"done": True, "task_id": "t"})]
    assert (await service.run(value.id, "dev", body))["id"] == result["id"]
    assert len(platform.test_writes) == 1
    with pytest.raises(AccessDenied):
        await service.run(value.id, "dev", body.model_copy(update={"confirm_actions": False}))
    with pytest.raises(AccessDenied):
        await service.run(value.id, "dev", body.model_copy(update={"mode": "fixture"}))


@pytest.mark.asyncio
async def test_missing_binding_blocks_action_and_records_failure(platform):
    await enable(platform)
    service = ModuleFlowService(platform, FlowRepository())
    await service.save(draft(nodes=[{"id": "write", "module_id": "action_progress", "operation": "action",
        "action": "plan.task.set_done", "bindings": {"task_id": "$input/missing"}}]), "dev")
    result = await service.run("test_flow", "dev", ModuleFlowRunRequest(mode="live", confirm_actions=True, request_id="request_001"))
    assert result["status"] == "failed" and result["trace"][0]["status"] == "failed"
    assert not result["action_committed"] and platform.test_writes == []


@pytest.mark.asyncio
async def test_unpublished_user_access_and_pinned_versions(platform):
    await enable(platform)
    service = ModuleFlowService(platform, FlowRepository())
    await service.save(draft(), "dev")
    body = ModuleFlowRunRequest(mode="live", request_id="request_001")
    with pytest.raises(ResourceNotFound):
        await service.run("test_flow", "alice", body, published=True)
    await service.publish("test_flow", 1, "dev")
    value = await service.run("test_flow", "alice", body, published=True)
    assert value["outputs"]["read"]["data"]["tasks"][0]["text"] == "alice"
    platform.repository.policies["action_progress"]["enabled"] = False
    with pytest.raises(AccessDenied):
        await service.run("test_flow", "alice", body, published=True)
    platform.repository.policies["action_progress"]["enabled"] = True
    definition = platform.modules["action_progress"]
    platform.modules["action_progress"] = replace(definition, manifest=definition.manifest.model_copy(update={"version": "2.0.0"}))
    with pytest.raises(DuplicateResource):
        await service.run("test_flow", "alice", body.model_copy(update={"request_id": "request_002"}), published=True)


def test_exact_dependencies_reject_missing_versions_and_cycles(platform, tmp_path):
    original = platform.modules["action_progress"]
    manifests = {}
    for mid in ("action_progress", "dependent_card"):
        folder = tmp_path / mid
        shutil.copytree(original.root, folder)
        manifests[mid] = {**original.manifest.model_dump(), "id": mid, "tool": f"{mid}.read", "dependencies": {}}
    def save():
        for mid, manifest in manifests.items():
            (tmp_path / mid / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    manifests["action_progress"]["dependencies"] = {"dependent_card": manifests["dependent_card"]["version"]}
    save()
    assert inspect_modules(tmp_path)["passed"]
    manifests["dependent_card"]["version"] = "9.0.0"
    save()
    assert not inspect_modules(tmp_path)["passed"]
    manifests["dependent_card"]["version"] = original.manifest.version
    manifests["dependent_card"]["dependencies"] = {"action_progress": original.manifest.version}
    save()
    assert not inspect_modules(tmp_path)["passed"]
    manifests["dependent_card"]["dependencies"] = {}
    manifests["action_progress"]["dependencies"] = {"absent_module": "1.0.0"}
    save()
    assert not inspect_modules(tmp_path)["passed"]


def test_workflow_http_roles_publishing_and_user_identity(platform):
    import asyncio
    asyncio.run(enable(platform))
    platform.flows = ModuleFlowService(platform, FlowRepository())
    app = create_app()
    app.state.module_platform = platform
    with TestClient(app) as client:
        def headers(role):
            return {"Authorization": f"Bearer {role}"}
        assert client.get("/api/v1/developer/capabilities", headers=headers("student")).status_code == 401
        assert client.get("/api/v1/developer/capabilities", headers=headers("dev")).status_code == 200
        value = client.post("/api/v1/developer/workflows", headers=headers("dev"), json=draft().model_dump())
        assert value.status_code == 200 and value.json()["data"]["owner"] == "dev"
        body = {"mode": "live", "request_id": "student_001"}
        assert client.post("/api/v1/app/workflows/test_flow/run", headers=headers("student"), json=body).status_code == 404
        assert client.post("/api/v1/developer/workflows/test_flow/publish", headers=headers("student"), json={"expected_revision": 1}).status_code == 401
        assert client.post("/api/v1/developer/workflows/test_flow/publish", headers=headers("dev"), json={"expected_revision": 1}).status_code == 200
        result = client.post("/api/v1/app/workflows/test_flow/run", headers=headers("student"), json=body)
        assert result.status_code == 200
        assert result.json()["data"]["outputs"]["read"]["data"]["tasks"][0]["text"] == "student"
        assert client.post("/api/v1/app/workflows/test_flow/run", headers=headers("student"), json={**body, "user_id": "admin"}).status_code == 422


@pytest.mark.asyncio
async def test_unpublish_preserves_history_and_blocks_new_and_replayed_user_runs(platform):
    await enable(platform)
    repository = FlowRepository()
    service = ModuleFlowService(platform, repository)
    await service.save(draft(), "dev")
    await service.publish("test_flow", 1, "dev")
    request = ModuleFlowRunRequest(mode="live", request_id="retained_run")
    await service.run("test_flow", "student", request, published=True)
    history = copy.deepcopy((repository.published, repository.receipts))
    with pytest.raises(AccessDenied):
        await service.unpublish("test_flow", 1, "other")
    with pytest.raises(DuplicateResource):
        await service.unpublish("test_flow", 2, "dev")
    assert (await repository.get("test_flow"))["published_revision"] == 1
    # Unpublish must work even when its formerly pinned module is unavailable.
    platform.modules.pop("action_progress")
    result = await service.unpublish("test_flow", 1, "dev")
    assert result["published_revision"] is None and result["revision"] == 1
    assert result["definition"] == draft().model_dump(include={"input_schema", "nodes"})
    assert (repository.published, repository.receipts) == history
    for body in (request, request.model_copy(update={"request_id": "new_request"})):
        with pytest.raises(ResourceNotFound):
            await service.run("test_flow", "student", body, published=True)
    assert await repository.runs("test_flow", "student")
    assert platform.test_writes == []


def test_unpublish_http_owner_admin_role_and_revision_checks(platform):
    platform.test_roles["other"] = platform.test_roles["dev"]
    platform.flows = ModuleFlowService(platform, FlowRepository())
    app = create_app()
    app.state.module_platform = platform
    with TestClient(app) as client:
        def call(path, actor, body):
            return client.post(f"/api/v1/developer/workflows{path}",
                headers={"Authorization": f"Bearer {actor}"}, json=body)
        assert call("", "dev", draft().model_dump()).status_code == 200
        assert call("/test_flow/publish", "dev", {"expected_revision": 1}).status_code == 200
        for actor in ("student", "other"):
            assert call("/test_flow/unpublish", actor, {"expected_revision": 1}).status_code == 401
        assert call("/test_flow/unpublish", "dev", {"expected_revision": 2}).status_code == 409
        assert call("/test_flow/unpublish", "dev", {"expected_revision": 0}).status_code == 422
        assert call("/test_flow/unpublish", "dev", {"expected_revision": 1}).json()["data"]["published_revision"] is None
        assert call("/test_flow/publish", "dev", {"expected_revision": 1}).status_code == 200
        assert call("/test_flow/unpublish", "admin", {"expected_revision": 1}).json()["data"]["published_revision"] is None
        platform.test_roles["dev"] = platform.test_roles["student"]
        assert call("/test_flow/unpublish", "dev", {"expected_revision": 1}).status_code == 401


def test_skill_preview_reports_business_input_mismatch_with_module_and_field(platform):
    app = create_app()
    app.state.module_platform = platform
    with TestClient(app) as client:
        response = client.post("/api/v1/developer/modules/plan_progress_skill/preview",
            headers={"Authorization": "Bearer dev"}, json={"mode": "fixture", "fixture": "normal", "input": {"expected_total": 999}})
    result = response.json()
    assert response.status_code == 422 and result["code"] == 1001
    assert "plan_progress_skill" in result["message"] and "expected_total" in result["message"]
    assert "backend.py.load" in result["message"]


@pytest.mark.parametrize("stage", ["load", "validate"])
def test_module_pydantic_errors_have_field_paths_without_echoing_values(platform, stage):
    from pydantic import BaseModel

    class Output(BaseModel):
        total: int

    def invalid(value):
        return Output.model_validate({"total": "PRIVATE_INPUT_MARKER"})

    async def load(context):
        return invalid(context)

    definition = platform.modules["action_progress"]
    changes = {"load": load} if stage == "load" else {"validate": invalid}
    platform.modules["action_progress"] = replace(definition, **changes)
    app = create_app()
    app.state.module_platform = platform
    with TestClient(app) as client:
        response = client.post("/api/v1/developer/modules/action_progress/preview",
            headers={"Authorization": "Bearer dev"}, json={"mode": "fixture"})
    result = response.json()
    assert response.status_code == 422 and result["code"] == 1001
    assert "action_progress" in result["message"] and "total" in result["message"]
    assert "PRIVATE_INPUT_MARKER" not in result["message"]


@pytest.mark.parametrize("error,status", [(RuntimeError("unknown failure"), 500), (KeyError("missing"), 500),
    (DuplicateResource("version changed"), 409), (AccessDenied("revoked"), 401)])
def test_module_unexpected_errors_and_platform_errors_keep_their_http_classification(platform, error, status):
    async def load(context):
        raise error

    platform.modules["action_progress"] = replace(platform.modules["action_progress"], load=load)
    app = create_app()
    app.state.module_platform = platform
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/developer/modules/action_progress/preview",
            headers={"Authorization": "Bearer dev"}, json={"mode": "fixture"})
    assert response.status_code == status


@pytest.mark.parametrize("binding", ["progress/data/missing", "progress/data/total/child", "progress/data/total"])
@pytest.mark.asyncio
async def test_obvious_bad_binding_paths_and_types_fail_before_publication(platform, binding):
    definition = platform.modules["action_progress"]
    producer = definition.manifest.model_copy(update={"output_schema": {"type": "object", "additionalProperties": False,
        "properties": {"total": {"type": "integer"}}}})
    platform.modules["action_progress"] = replace(definition, manifest=producer)
    consumer = producer.model_copy(update={"id": "consumer", "tool": "consumer.read",
        "input_schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}, "additionalProperties": False}})
    platform.modules["consumer"] = replace(definition, manifest=consumer)
    service = ModuleFlowService(platform, FlowRepository())
    with pytest.raises(InvalidRequest):
        await service.save(draft(nodes=[{"id": "progress", "module_id": "action_progress"},
            {"id": "consume", "module_id": "consumer", "bindings": {"text": binding}}]), "dev")
    with pytest.raises(InvalidRequest):
        await service.save(draft(nodes=[{"id": "consume", "module_id": "consumer"}]), "dev")


@pytest.mark.asyncio
async def test_action_readback_requires_valid_query_input_before_writing(platform):
    await enable(platform)
    definition = platform.modules["action_progress"]
    manifest = definition.manifest.model_copy(update={"input_schema": {"type": "object", "required": ["limit"],
        "properties": {"limit": {"type": "integer"}}, "additionalProperties": False}})
    platform.modules["action_progress"] = replace(definition, manifest=manifest)
    service = ModuleFlowService(platform, FlowRepository())
    action = {"id": "complete", "module_id": "action_progress", "operation": "action", "action": "plan.task.set_done",
              "input": {"task_id": "t", "done": True}}
    await service.save(draft(nodes=[action]), "dev")
    result = await service.run("test_flow", "dev", ModuleFlowRunRequest(mode="live", confirm_actions=True, request_id="required_001"))
    assert result["status"] == "failed" and platform.test_writes == []
    await service.save(draft(expected_revision=1, nodes=[{"id": "progress", "module_id": "action_progress", "input": {"limit": 2}}, action]), "dev")
    result = await service.run("test_flow", "dev", ModuleFlowRunRequest(mode="live", confirm_actions=True, request_id="required_002"))
    assert result["status"] == "succeeded" and result["action_committed"]
    assert len(platform.test_writes) == 1
