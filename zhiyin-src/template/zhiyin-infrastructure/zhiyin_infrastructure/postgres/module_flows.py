"""Optimistic draft updates and durable, deduplicated workflow execution."""
import json
from uuid import uuid4

import asyncpg

from zhiyin_kernel.errors import DuplicateResource, ResourceNotFound


# The blue/green executor takes the matching exclusive session lock while it
# validates published snapshots and switches the active runtime revision.
WORKFLOW_PUBLICATION_LOCK = 741517501


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _view(row):
    if row is None:
        raise ResourceNotFound("工作流不存在")
    return {"id": row["id"], "name": row["name"], "owner": row["owner"], "revision": row["revision"],
            "published_revision": row["published_revision"], "definition": _json(row["definition"]),
            "updated_at": row["updated_at"].isoformat()}


class PostgresModuleFlowRepository:
    def __init__(self, database, *, revision):
        self.db = database
        self.revision = revision

    async def _publication_guard(self, connection):
        acquired = await connection.fetchval("SELECT pg_try_advisory_xact_lock_shared($1)", WORKFLOW_PUBLICATION_LOCK)
        if not acquired:
            raise DuplicateResource("平台正在更新，请稍后刷新后再调整工作流发布状态")
        active = await connection.fetchrow("SELECT active_revision FROM biz_module_runtime_revision WHERE id=1")
        if active is None:
            raise DuplicateResource("平台运行版本尚未初始化，请稍后重试")
        # An empty singleton is the one-time migration path for legacy stacks.
        # Once deployment has set it, stale API processes must fail closed.
        if active["active_revision"] and active["active_revision"] != self.revision:
            raise DuplicateResource("平台版本已更新，请刷新后重新调整工作流发布状态")

    async def list(self):
        return [_view(row) for row in await self.db.fetch("SELECT * FROM biz_module_workflow ORDER BY updated_at DESC")]

    async def get(self, workflow_id, *, published=False):
        row = await self.db.fetchrow("SELECT * FROM biz_module_workflow WHERE id=$1", workflow_id)
        value = _view(row)
        if published:
            if value["published_revision"] is None:
                raise ResourceNotFound("工作流尚未发布")
            snapshot = await self.db.fetchrow("SELECT definition FROM biz_module_workflow_version WHERE workflow_id=$1 AND revision=$2", workflow_id, value["published_revision"])
            if snapshot is None:
                raise ResourceNotFound("已发布的工作流版本不存在")
            value.update(definition=_json(snapshot["definition"]), revision=value["published_revision"])
        return value

    async def save(self, draft, actor):
        definition = json.dumps({"input_schema": draft["input_schema"], "nodes": draft["nodes"]})
        try:
            if draft["expected_revision"] == 0:
                row = await self.db.fetchrow("INSERT INTO biz_module_workflow(id,name,owner,definition) VALUES($1,$2,$3,$4::jsonb) RETURNING *", draft["id"], draft["name"], actor, definition)
            else:
                row = await self.db.fetchrow("UPDATE biz_module_workflow SET name=$2,definition=$3::jsonb,revision=revision+1,updated_at=now() WHERE id=$1 AND revision=$4 RETURNING *", draft["id"], draft["name"], definition, draft["expected_revision"])
                if row is None:
                    raise DuplicateResource("工作流已被其他人修改，请刷新后合并")
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateResource("工作流编号已存在") from exc
        return _view(row)

    async def publish(self, workflow_id, revision, definition, actor):
        async with self.db.transaction() as connection:
            await self._publication_guard(connection)
            row = await connection.fetchrow("SELECT * FROM biz_module_workflow WHERE id=$1 FOR UPDATE", workflow_id)
            current = _view(row)
            if current["revision"] != revision:
                raise DuplicateResource("工作流版本已变化，请刷新后发布")
            previous = await connection.fetchrow("SELECT definition FROM biz_module_workflow_version WHERE workflow_id=$1 AND revision=$2", workflow_id, revision)
            if previous and _json(previous["definition"]) != definition:
                raise DuplicateResource("该工作流版本已发布，引用版本变化后请保存新草稿")
            await connection.execute("INSERT INTO biz_module_workflow_version(workflow_id,revision,definition,published_by) VALUES($1,$2,$3::jsonb,$4) ON CONFLICT DO NOTHING", workflow_id, revision, json.dumps(definition), actor)
            row = await connection.fetchrow("UPDATE biz_module_workflow SET published_revision=$2,updated_at=now() WHERE id=$1 RETURNING *", workflow_id, revision)
        return _view(row)

    async def unpublish(self, workflow_id, revision, actor):
        async with self.db.transaction() as connection:
            await self._publication_guard(connection)
            row = await connection.fetchrow("SELECT * FROM biz_module_workflow WHERE id=$1 FOR UPDATE", workflow_id)
            current = _view(row)
            if current["revision"] != revision:
                raise DuplicateResource("工作流版本已变化，请刷新后暂停发布")
            row = await connection.fetchrow("UPDATE biz_module_workflow SET published_revision=NULL,updated_at=now() WHERE id=$1 RETURNING *", workflow_id)
        return _view(row)

    async def begin_run(self, workflow_id, revision, actor, request_id, digest, mode):
        run = {"id": uuid4().hex, "workflow_id": workflow_id, "revision": revision, "mode": mode,
               "status": "running", "outputs": {}, "trace": [], "error": "", "action_committed": False}
        async with self.db.transaction() as connection:
            inserted = await connection.fetchrow("INSERT INTO biz_module_workflow_run(id,workflow_id,revision,actor,request_id,input_digest,result) VALUES($1,$2,$3,$4,$5,$6,$7::jsonb) ON CONFLICT(workflow_id,actor,request_id) DO NOTHING RETURNING id", run["id"], workflow_id, revision, actor, request_id, digest, json.dumps(run))
            row = await connection.fetchrow("SELECT input_digest,result FROM biz_module_workflow_run WHERE workflow_id=$1 AND actor=$2 AND request_id=$3", workflow_id, actor, request_id)
            if row["input_digest"] != digest:
                raise DuplicateResource("同一请求编号不能用于不同的工作流输入或版本")
        return _json(row["result"]), inserted is not None

    async def update_run(self, run):
        await self.db.execute("UPDATE biz_module_workflow_run SET result=$2::jsonb,updated_at=now() WHERE id=$1", run["id"], json.dumps(run))
        return run

    async def runs(self, workflow_id, actor=None):
        rows = await self.db.fetch("SELECT result FROM biz_module_workflow_run WHERE workflow_id=$1 AND ($2::text IS NULL OR actor=$2) ORDER BY created_at DESC LIMIT 100", workflow_id, actor)
        return [_json(row["result"]) for row in rows]
