"""Mutations recheck live project/account permissions inside their transaction."""
from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from zhiyin_infrastructure.postgres.developer import PostgresDeveloperRepository
from zhiyin_kernel.errors import AccessDenied, DuplicateResource, InvalidRequest


class Database:
    """Small persistence double; permission changes land at transaction entry.

    API authorization has already happened at that point, reproducing the
    original check/use window without relying on scheduler timing.
    """

    def __init__(self):
        now = datetime.now(timezone.utc)
        self.project = {
            "id": "progress", "name": "Progress", "description": "", "owner": "owner",
            "members": '["member"]', "trusted": True, "auto_deploy": True,
            "revision": 2, "created_at": now, "updated_at": now,
        }
        self.roles = {"owner": "developer", "member": "developer", "administrator": "admin"}
        self.version = {
            "id": "version", "project_id": "progress", "version": "1.0.0", "channel": "main",
            "base_version_id": None, "base_commit": "base", "digest": "digest", "actor": "member",
            "request_id": "request", "status": "passed", "stage": "passed", "events": [],
            "manifest": {"id": "progress", "version": "1.0.0"}, "created_at": now,
            "candidate_commit": "candidate", "release_job_id": "", "report": {
                "rules_version": "3", "expected_revision": "installed",
                "gates": [{"name": name, "status": "passed"} for name in ("contracts", "tests", "build", "dataflow")],
                "dataflow": {"passed": True, "browser": {"gate": "browser", "rules_version": "1",
                    "passed": True, "revision": "candidate", "no_api_mocking": True,
                    "modules": {"progress": {"version": "1.0.0", "kind": "hybrid", "passed": True,
                        "checks": [{"fixture": fixture, "viewport": viewport, "passed": True}
                            for fixture in ("normal", "empty", "error") for viewport in ("desktop", "narrow")]}},
                    "errors": [], "network_failures": []}, "artifacts": {
                    "revision": "candidate", "api_image": "api@sha256:a", "web_image": "web@sha256:b",
                }},
            },
        }
        self.job = {
            "id": "job", "commit_sha": "candidate", "kind": "deploy", "actor": "member",
            "request_id": "version-version", "status": "queued", "stage": "", "lease": "",
            "result": {}, "events": [], "created_at": now,
        }
        self.in_transaction = False
        self.at_begin = lambda: None
        self.queries = []
        self.writes = []
        self.existing = None

    @asynccontextmanager
    async def transaction(self):
        assert not self.in_transaction
        self.at_begin()
        self.in_transaction = True
        try:
            yield self
        finally:
            self.in_transaction = False

    async def fetchrow(self, query, *args):
        assert self.in_transaction, "permission and write queries must share a transaction"
        query = " ".join(query.split())
        self.queries.append((query, args))
        if query.startswith("SELECT payload FROM biz_user_account"):
            assert query.endswith("FOR SHARE"), "role must remain locked through the mutation"
            role = self.roles.get(args[0])
            return {"payload": json.dumps({"role": role})} if role else None
        if query.startswith("SELECT * FROM biz_developer_project"):
            assert query.endswith(("FOR SHARE", "FOR UPDATE"))
            return deepcopy(self.project)
        if query.startswith("SELECT * FROM biz_developer_version WHERE id="):
            assert query.endswith("FOR NO KEY UPDATE"), "FK checks must not deadlock with uploads"
            return deepcopy(self.version)
        if query.startswith("SELECT * FROM biz_developer_version WHERE actor="):
            return deepcopy(self.existing)
        if query.startswith("SELECT id FROM biz_developer_version"):
            return None
        if query.startswith("SELECT * FROM biz_module_release"):
            return deepcopy(self.job)
        if query.startswith("UPDATE biz_developer_project"):
            if args[6] != self.project["revision"]:
                return None
            self.writes.append("project")
            self.project.update(name=args[1], description=args[2], members=args[3], trusted=args[4], auto_deploy=args[5])
            self.project["revision"] += 1
            return deepcopy(self.project)
        if query.startswith("INSERT INTO biz_developer_version"):
            self.writes.append("upload")
            return deepcopy(self.version)
        if query.startswith("UPDATE biz_developer_version"):
            self.writes.append("retry")
            self.version.update(status="queued", report=json.loads(args[1]))
            return deepcopy(self.version)
        if query.startswith("INSERT INTO biz_module_release"):
            self.writes.append("release")
            self.job["result"] = json.loads(args[4])
            return deepcopy(self.job)
        raise AssertionError(query)

    async def execute(self, query, *args):
        assert self.in_transaction
        self.writes.append("audit" if "biz_module_audit" in query else "attach_release")


def body(db, **changes):
    return {
        "name": "Changed", "description": "", "members": ["member"],
        "trusted": db.project["trusted"], "auto_deploy": db.project["auto_deploy"],
        "revision": db.project["revision"], **changes,
    }


async def mutate(repo, operation, actor="member", configuration=None, *, internal_worker=False):
    if operation == "upload":
        return await repo.create_version("progress", actor, {
            "request_id": "request", "channel": "main", "base_version_id": None, "base_commit": "base",
        }, b"zip", {"id": "progress", "version": "1.0.0"}, "digest")
    if operation == "retry":
        return await repo.retry("version", actor, internal_worker=internal_worker)
    if operation == "release":
        return await repo.release("version", actor, "installed", internal_worker=internal_worker)
    return await repo.update_project("progress", configuration, actor)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "retry", "release"])
async def test_membership_revoked_after_api_check_blocks_mutation(operation):
    db = Database()
    assert "member" in json.loads(db.project["members"])
    db.at_begin = lambda: db.project.update(members="[]")
    with pytest.raises(AccessDenied, match="成员"):
        await mutate(PostgresDeveloperRepository(db), operation)
    assert not db.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "retry", "release", "configure"])
@pytest.mark.parametrize("new_role", ["student", None])
async def test_account_demotion_or_deletion_blocks_even_project_owner(operation, new_role):
    db = Database()
    configuration = body(db)
    db.at_begin = lambda: db.roles.update(owner=new_role)
    with pytest.raises(AccessDenied, match="权限已撤销"):
        await mutate(PostgresDeveloperRepository(db), operation, "owner", configuration)
    assert not db.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "retry", "release"])
async def test_idempotent_receipt_does_not_bypass_revoked_membership(operation):
    db = Database()
    db.project["members"] = "[]"
    db.existing = deepcopy(db.version)
    db.version.update(status="queued", release_job_id="job")
    with pytest.raises(AccessDenied):
        await mutate(PostgresDeveloperRepository(db), operation)
    assert not db.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "retry", "release"])
@pytest.mark.parametrize("actor", ["member", "owner", "administrator"])
async def test_current_member_owner_and_admin_can_mutate(operation, actor):
    db = Database()
    result = await mutate(PostgresDeveloperRepository(db), operation, actor)
    assert result["id"]
    assert operation in db.writes
    assert any("biz_user_account" in query and args == (actor,) for query, args in db.queries)


@pytest.mark.asyncio
async def test_member_cannot_manage_and_demoted_admin_cannot_keep_admin_capabilities():
    db = Database()
    repo = PostgresDeveloperRepository(db)
    with pytest.raises(AccessDenied, match="管理"):
        await repo.update_project("progress", body(db), "member")
    db.roles["administrator"] = "developer"
    with pytest.raises(AccessDenied, match="管理"):
        await repo.update_project("progress", body(db), "administrator")
    assert not db.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [{"trusted": False, "auto_deploy": False}, {"auto_deploy": False}])
async def test_owner_cannot_change_trust_or_auto_deployment(changed):
    db = Database()
    with pytest.raises(AccessDenied, match="管理员"):
        await PostgresDeveloperRepository(db).update_project("progress", body(db, **changed), "owner")
    assert not db.writes


@pytest.mark.asyncio
async def test_configuration_rechecks_member_roles_and_keeps_revision_cas():
    db = Database()
    repo = PostgresDeveloperRepository(db)
    with pytest.raises(DuplicateResource):
        await repo.update_project("progress", body(db, revision=1), "administrator")
    assert not db.writes
    db.roles["member"] = "student"
    with pytest.raises(AccessDenied):
        await repo.update_project("progress", body(db), "owner")
    assert not db.writes
    db.roles["member"] = "developer"
    updated = await repo.update_project("progress", body(db), "owner")
    assert updated["revision"] == 3


@pytest.mark.asyncio
async def test_admin_can_change_trust_but_cannot_enable_untrusted_auto_deployment():
    db = Database()
    repo = PostgresDeveloperRepository(db)
    with pytest.raises(InvalidRequest):
        await repo.update_project("progress", body(db, trusted=False, auto_deploy=True), "administrator")
    assert not db.writes
    updated = await repo.update_project("progress", body(db, trusted=False, auto_deploy=False), "administrator")
    assert not updated["trusted"]
    assert not updated["auto_deploy"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["retry", "release"])
async def test_internal_worker_keeps_existing_trusted_host_path(operation):
    db = Database()
    await mutate(PostgresDeveloperRepository(db), operation, "source-worker", internal_worker=True)
    assert operation in db.writes
    assert not any("biz_user_account" in query for query, _ in db.queries)


@pytest.mark.asyncio
@pytest.mark.parametrize("project_changes", [{"trusted": False}, {"auto_deploy": False}])
async def test_worker_release_cannot_bypass_current_project_authorization(project_changes):
    db = Database()
    db.at_begin = lambda: db.project.update(**project_changes)
    with pytest.raises(AccessDenied):
        await mutate(PostgresDeveloperRepository(db), "release", "source-worker", internal_worker=True)
    assert not db.writes


@pytest.mark.asyncio
async def test_worker_name_is_not_an_upload_or_configuration_permission():
    db = Database()
    repo = PostgresDeveloperRepository(db)
    for operation in ("upload", "configure"):
        with pytest.raises(AccessDenied):
            await mutate(repo, operation, "source-worker", body(db))
    assert not db.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["retry", "release"])
async def test_account_named_source_worker_cannot_bypass_membership(operation):
    db = Database()
    db.roles["source-worker"] = "developer"
    with pytest.raises(AccessDenied, match="成员"):
        await mutate(PostgresDeveloperRepository(db), operation, "source-worker")
    assert not db.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["legacy_rules", "missing_browser", "failed_browser", "wrong_revision", "untyped_success"])
async def test_release_requires_current_rules_and_matching_successful_browser_attestation(defect):
    db = Database()
    report = db.version["report"]
    if defect == "legacy_rules":
        report["rules_version"] = "2"
    elif defect == "missing_browser":
        report["dataflow"].pop("browser")
    elif defect == "failed_browser":
        report["dataflow"]["browser"]["passed"] = False
    elif defect == "wrong_revision":
        report["dataflow"]["browser"]["revision"] = "another-candidate"
    else:
        report["dataflow"]["browser"]["passed"] = "true"
    with pytest.raises(InvalidRequest, match="重新验收"):
        await mutate(PostgresDeveloperRepository(db), "release")
    assert not db.writes


@pytest.mark.asyncio
async def test_release_carries_rules_three_and_accepted_images():
    db = Database()
    job = await mutate(PostgresDeveloperRepository(db), "release")
    assert job["result"]["rules_version"] == "3"
    assert job["result"]["accepted_artifacts"] == db.version["report"]["dataflow"]["artifacts"]
