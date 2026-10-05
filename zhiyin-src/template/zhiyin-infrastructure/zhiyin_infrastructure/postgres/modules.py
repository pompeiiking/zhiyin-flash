"""Transactional policies, idempotent jobs and fenced executor leases."""
from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from zhiyin_infrastructure.postgres.database import PostgresDatabase
from zhiyin_kernel.errors import DuplicateResource, ResourceNotFound


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _job(row):
    if row is None:
        return None
    return {"id": row["id"], "commit": row["commit_sha"], "kind": row["kind"], "actor": row["actor"],
            "request_id": row["request_id"], "status": row["status"], "stage": row["stage"],
            "lease": row["lease"], "result": _json(row["result"]), "events": _json(row["events"]),
            "created_at": row["created_at"].isoformat()}


class PostgresModuleRepository:
    def __init__(self, db: PostgresDatabase):
        self.db = db

    async def seed(self, module_id: str, policy: dict):
        await self.db.execute("INSERT INTO biz_module_policy(module_id,payload,updated_by) VALUES($1,$2::jsonb,'bootstrap') ON CONFLICT DO NOTHING", module_id, json.dumps(policy))

    async def policy(self, module_id: str) -> dict:
        row = await self.db.fetchrow("SELECT payload,revision FROM biz_module_policy WHERE module_id=$1", module_id)
        return {**_json(row["payload"]), "revision": row["revision"]} if row else {"revision": 0}

    async def save_policy(self, module_id: str, policy: dict, actor: str):
        expected = policy.pop("revision")
        async with self.db.transaction() as conn:
            if expected == 0:
                try:
                    await conn.execute("INSERT INTO biz_module_policy(module_id,payload,updated_by) VALUES($1,$2::jsonb,$3)", module_id, json.dumps(policy), actor)
                except asyncpg.UniqueViolationError as exc:
                    raise DuplicateResource("配置已更新，请刷新后再保存") from exc
                revision = 1
            else:
                row = await conn.fetchrow("UPDATE biz_module_policy SET payload=$2::jsonb,revision=revision+1,updated_by=$3,updated_at=now() WHERE module_id=$1 AND revision=$4 RETURNING revision", module_id, json.dumps(policy), actor, expected)
                if row is None:
                    raise DuplicateResource("配置已更新，请刷新后再保存")
                revision = row["revision"]
            await conn.execute("INSERT INTO biz_module_audit(actor,subject,action,payload) VALUES($1,$2,'policy',$3::jsonb)", actor, module_id, json.dumps(policy))
        return {**policy, "revision": revision}

    async def record_check(self, actor: str, result: dict):
        check_id = uuid4().hex
        await self.db.execute("INSERT INTO biz_module_check(id,actor,result) VALUES($1,$2,$3::jsonb)", check_id, actor, json.dumps(result))
        return {"id": check_id, "actor": actor, **result}

    async def checks(self):
        rows = await self.db.fetch("SELECT * FROM biz_module_check ORDER BY created_at DESC LIMIT 50")
        return [{"id": x["id"], "actor": x["actor"], "created_at": x["created_at"].isoformat(), **_json(x["result"])} for x in rows]

    async def create_job(self, actor: str, body: dict):
        async with self.db.transaction() as conn:
            await conn.execute("INSERT INTO biz_module_release(id,commit_sha,kind,actor,request_id) VALUES($1,$2,$3,$4,$5) ON CONFLICT(actor,request_id) DO NOTHING", uuid4().hex, body["commit"], body["kind"], actor, body["request_id"])
            row = await conn.fetchrow("SELECT * FROM biz_module_release WHERE actor=$1 AND request_id=$2", actor, body["request_id"])
            if row["commit_sha"] != body["commit"] or row["kind"] != body["kind"]:
                raise DuplicateResource("相同请求编号不能用于不同提交或操作")
        return _job(row)

    async def jobs(self):
        return [_job(x) for x in await self.db.fetch("SELECT * FROM biz_module_release ORDER BY created_at DESC LIMIT 100")]

    async def approve(self, job_id: str, actor: str):
        try:
            async with self.db.transaction() as conn:
                row = await conn.fetchrow("SELECT * FROM biz_module_release WHERE id=$1 FOR UPDATE", job_id)
                if not row:
                    raise ResourceNotFound("发布任务不存在")
                if row["status"] == "requested":
                    event = json.dumps([{"stage": "approved", "message": f"管理员 {actor} 已确认"}])
                    row = await conn.fetchrow("UPDATE biz_module_release SET status='queued',events=events || $2::jsonb,updated_at=now() WHERE id=$1 RETURNING *", job_id, event)
                return _job(row)
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateResource("测试环境已有执行中的任务，请等它结束") from exc

    async def claim(self):
        async with self.db.transaction() as conn:
            await conn.execute("""UPDATE biz_module_release r SET status='failed',stage='authorization_revoked',updated_at=now(),
                events=r.events || '[{"stage":"authorization_revoked","message":"项目运行授权已撤销，取消排队发布"}]'::jsonb
                FROM biz_developer_version v JOIN biz_developer_project p ON p.id=v.project_id
                WHERE r.status='queued' AND r.result->>'version_id'=v.id AND NOT p.trusted""")
            row = await conn.fetchrow("SELECT * FROM biz_module_release WHERE status='queued' OR (status='running' AND lease_until < now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
            if not row:
                return None
            lease = uuid4().hex
            claimed = await conn.fetchrow("UPDATE biz_module_release SET status='running',lease=$2,lease_until=now()+interval '90 seconds',updated_at=now() WHERE id=$1 RETURNING *", row["id"], lease)
            result = _job(claimed)
            result["result"]["resuming"] = row["status"] == "running"
            return result

    async def authorization(self, job_id):
        row = await self.db.fetchrow("SELECT result FROM biz_module_release WHERE id=$1", job_id)
        if row is None:
            raise ResourceNotFound("发布任务不存在")
        version_id = _json(row["result"]).get("version_id")
        if not version_id:
            return {"allowed": True, "reason": "固定提交发布"}
        allowed = await self.db.fetchval("SELECT p.trusted FROM biz_developer_version v JOIN biz_developer_project p ON p.id=v.project_id WHERE v.id=$1", version_id)
        return {"allowed": bool(allowed), "reason": "项目运行授权有效" if allowed else "项目运行授权已经撤销"}

    async def update_job(self, job_id: str, lease: str, update: dict):
        event = update.get("event")
        row = await self.db.fetchrow("""UPDATE biz_module_release SET
            status=COALESCE($3,status), stage=COALESCE($4,stage),
            result=result || $5::jsonb, events=events || $6::jsonb,
            lease_until=now()+interval '90 seconds',updated_at=now()
            WHERE id=$1 AND lease=$2 AND status='running' AND lease_until>now() RETURNING *""",
            job_id, lease, update.get("status"), update.get("stage"),
            json.dumps(update.get("result", {})), json.dumps([event] if event else []))
        if row is None:
            raise DuplicateResource("执行租约已失效，停止当前操作并重新核对环境")
        return _job(row)
