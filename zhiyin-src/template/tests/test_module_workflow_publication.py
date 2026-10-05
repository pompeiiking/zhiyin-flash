"""Publication transaction ordering and revision fencing; real PG is checked separately."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from zhiyin_infrastructure.postgres.module_flows import PostgresModuleFlowRepository, WORKFLOW_PUBLICATION_LOCK
from zhiyin_kernel.errors import DuplicateResource, ResourceNotFound


class Database:
    def __init__(self):
        self.row = {"id": "flow", "name": "Flow", "owner": "owner", "revision": 2,
            "definition": {"nodes": [{"module_id": "progress", "module_version": "1.0.0"}]},
            "published_revision": 1, "updated_at": datetime.now(timezone.utc)}
        self.snapshots = {1: {"nodes": [{"module_id": "progress", "module_version": "0.9.0"}]}}
        self.active_revision = "new-build"
        self.lock_available = True
        self.in_transaction = False
        self.queries, self.writes = [], []

    @asynccontextmanager
    async def transaction(self):
        assert not self.in_transaction
        self.in_transaction = True
        snapshot = deepcopy((self.row, self.snapshots))
        try:
            yield self
        except Exception:
            self.row, self.snapshots = snapshot
            raise
        finally:
            self.in_transaction = False

    async def fetchval(self, sql, *args):
        assert self.in_transaction
        self.queries.append((sql, args))
        assert sql == "SELECT pg_try_advisory_xact_lock_shared($1)"
        assert args == (WORKFLOW_PUBLICATION_LOCK,)
        return self.lock_available

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        if "FROM biz_module_runtime_revision" in sql:
            assert self.in_transaction
            assert self.queries[-2][0] == "SELECT pg_try_advisory_xact_lock_shared($1)"
            return {"active_revision": self.active_revision} if self.active_revision is not None else None
        if sql.startswith("SELECT * FROM biz_module_workflow"):
            if "FOR UPDATE" in sql:
                assert self.in_transaction
                assert "FROM biz_module_runtime_revision" in self.queries[-2][0]
            return deepcopy(self.row)
        if sql.startswith("SELECT definition FROM biz_module_workflow_version"):
            return {"definition": deepcopy(self.snapshots[args[1]])} if args[1] in self.snapshots else None
        if sql.startswith("UPDATE biz_module_workflow SET published_revision="):
            assert self.in_transaction
            self.writes.append(sql)
            self.row["published_revision"] = None if "published_revision=NULL" in sql else args[1]
            return deepcopy(self.row)
        if sql.startswith("UPDATE biz_module_workflow SET name="):
            assert not self.in_transaction
            self.row.update(name=args[1], definition=json.loads(args[2]), revision=self.row["revision"] + 1)
            return deepcopy(self.row)
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        assert self.in_transaction
        assert sql.startswith("INSERT INTO biz_module_workflow_version")
        self.queries.append((sql, args))
        self.writes.append(sql)
        self.snapshots.setdefault(args[1], json.loads(args[2]))


async def mutate(repo, operation):
    if operation == "publish":
        return await repo.publish("flow", 2, {"nodes": []}, "owner")
    return await repo.unpublish("flow", 2, "owner")


@pytest.mark.parametrize("operation", ["publish", "unpublish"])
@pytest.mark.parametrize("active_revision", ["", "new-build"])
async def test_current_and_initial_legacy_builds_can_change_publication(operation, active_revision):
    db = Database()
    db.active_revision = active_revision
    result = await mutate(PostgresModuleFlowRepository(db, revision="new-build"), operation)
    assert result["published_revision"] == (2 if operation == "publish" else None)
    assert result["revision"] == 2
    assert db.snapshots[1]["nodes"][0]["module_version"] == "0.9.0"


@pytest.mark.parametrize("operation", ["publish", "unpublish"])
async def test_deployment_exclusive_lock_rejects_without_waiting_or_reading_workflow(operation):
    db = Database()
    db.lock_available = False
    with pytest.raises(DuplicateResource, match="正在更新"):
        await mutate(PostgresModuleFlowRepository(db, revision="new-build"), operation)
    assert len(db.queries) == 1 and not db.writes


@pytest.mark.parametrize("operation", ["publish", "unpublish"])
@pytest.mark.parametrize("active_revision", ["other-build", None])
async def test_stale_api_and_missing_runtime_singleton_cannot_publish_or_unpublish(operation, active_revision):
    db = Database()
    db.active_revision = active_revision
    before = deepcopy((db.row, db.snapshots))
    with pytest.raises(DuplicateResource):
        await mutate(PostgresModuleFlowRepository(db, revision="new-build"), operation)
    assert (db.row, db.snapshots) == before and not db.writes
    assert len(db.queries) == 2


@pytest.mark.parametrize("operation", ["publish", "unpublish"])
async def test_revision_conflict_leaves_pointer_and_immutable_history_unchanged(operation):
    db = Database()
    db.row["revision"] = 3
    before = deepcopy((db.row, db.snapshots))
    with pytest.raises(DuplicateResource):
        await mutate(PostgresModuleFlowRepository(db, revision="new-build"), operation)
    assert (db.row, db.snapshots) == before and not db.writes


async def test_unpublish_only_removes_pointer_and_history_can_be_republished():
    db = Database()
    repo = PostgresModuleFlowRepository(db, revision="new-build")
    definition = deepcopy(db.row["definition"])
    await repo.publish("flow", 2, definition, "owner")
    history = deepcopy(db.snapshots)
    await repo.unpublish("flow", 2, "owner")
    with pytest.raises(ResourceNotFound, match="尚未发布"):
        await repo.get("flow", published=True)
    assert (await repo.get("flow"))["definition"] == definition
    assert db.snapshots == history
    await repo.publish("flow", 2, definition, "owner")
    assert db.snapshots == history
    with pytest.raises(DuplicateResource, match="该工作流版本已发布"):
        await repo.publish("flow", 2, {"nodes": []}, "owner")
    assert db.snapshots == history


async def test_draft_save_remains_available_during_deployment():
    db = Database()
    db.lock_available = False
    repo = PostgresModuleFlowRepository(db, revision="old-build")
    result = await repo.save({"id": "flow", "name": "New draft", "expected_revision": 2,
        "input_schema": {}, "nodes": []}, "owner")
    assert result["revision"] == 3 and result["published_revision"] == 1
    assert all("advisory" not in sql and "runtime_revision" not in sql for sql, _ in db.queries)
