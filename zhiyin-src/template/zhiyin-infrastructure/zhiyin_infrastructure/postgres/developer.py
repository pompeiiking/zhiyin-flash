"""Durable immutable packages, project CAS and fenced parallel acceptance jobs."""
from __future__ import annotations

import json
from uuid import uuid4

import asyncpg

from zhiyin_infrastructure.postgres.modules import _job, _json
from zhiyin_kernel.errors import AccessDenied, DuplicateResource, InvalidRequest, ResourceNotFound


def _project(row):
    if row is None:
        raise ResourceNotFound("模块项目不存在")
    value = dict(row)
    value["members"] = _json(value["members"])
    for key in ("created_at", "updated_at"):
        value[key] = value[key].isoformat()
    return value


def _version(row, package=False):
    if row is None:
        raise ResourceNotFound("模块版本不存在")
    keys = ("id", "project_id", "version", "channel", "base_version_id", "base_commit", "digest", "actor",
            "status", "stage", "candidate_commit", "release_job_id")
    value = {key: row[key] for key in keys}
    value.update({key: _json(row[key]) for key in ("manifest", "report", "events")})
    value["created_at"] = row["created_at"].isoformat()
    if package:
        value["package"] = row["package"]
    return value


async def _actor_role(conn, actor):
    # Keep a role revocation ordered with the mutation, using the authoritative
    # account row rather than the role cached by the API before this transaction.
    row = await conn.fetchrow("SELECT payload FROM biz_user_account WHERE id=$1 FOR SHARE", actor)
    role = _json(row["payload"]).get("role") if row else None
    if role not in {"developer", "admin"}:
        raise AccessDenied("开发者或管理员权限已撤销")
    return role


async def _authorize_project(conn, project, actor, *, manage=False, internal_worker=False):
    if project is None:
        raise ResourceNotFound("模块项目不存在")
    if internal_worker:
        return None
    role = await _actor_role(conn, actor)
    if role == "admin" or project["owner"] == actor:
        return role
    if not manage and actor in _json(project["members"]):
        return role
    raise AccessDenied("没有这个模块项目的管理权限" if manage else "不是此项目的开发成员")


class PostgresDeveloperRepository:
    def __init__(self, db):
        self.db = db

    async def projects(self, actor, admin=False):
        rows = await self.db.fetch("SELECT * FROM biz_developer_project WHERE $2 OR owner=$1 OR members ? $1 ORDER BY created_at DESC", actor, admin)
        return [_project(row) for row in rows]

    async def project(self, project_id):
        return _project(await self.db.fetchrow("SELECT * FROM biz_developer_project WHERE id=$1", project_id))

    async def create_project(self, body, actor):
        try:
            row = await self.db.fetchrow("INSERT INTO biz_developer_project(id,name,description,owner) VALUES($1,$2,$3,$4) RETURNING *", body["id"], body["name"], body["description"], actor)
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateResource("该模块项目已存在，请联系负责人添加成员") from exc
        return _project(row)

    async def update_project(self, project_id, body, actor):
        async with self.db.transaction() as conn:
            project = await conn.fetchrow("SELECT * FROM biz_developer_project WHERE id=$1 FOR UPDATE", project_id)
            role = await _authorize_project(conn, project, actor, manage=True)
            if role != "admin" and (body["trusted"] != project["trusted"] or body["auto_deploy"] != project["auto_deploy"]):
                raise AccessDenied("项目信任和自动发布策略由管理员配置")
            if body["auto_deploy"] and not body["trusted"]:
                raise InvalidRequest("启用自动发布前必须授权项目运行")
            for member in sorted(set(body["members"])):
                await _actor_role(conn, member)
            row = await conn.fetchrow("""UPDATE biz_developer_project SET name=$2,description=$3,members=$4::jsonb,
                trusted=$5,auto_deploy=$6,revision=revision+1,updated_at=now() WHERE id=$1 AND revision=$7 RETURNING *""",
                project_id, body["name"], body["description"], json.dumps(sorted(set(body["members"]))),
                body["trusted"], body["auto_deploy"], body["revision"])
            if row is None:
                raise DuplicateResource("项目配置已被其他人修改，请刷新后保存")
            await conn.execute("INSERT INTO biz_module_audit(actor,subject,action,payload) VALUES($1,$2,'project',$3::jsonb)", actor, project_id, json.dumps(body))
        return _project(row)

    async def versions(self, project_id):
        return [_version(row) for row in await self.db.fetch("SELECT * FROM biz_developer_version WHERE project_id=$1 ORDER BY created_at DESC LIMIT 100", project_id)]

    async def version(self, version_id, package=False):
        return _version(await self.db.fetchrow("SELECT * FROM biz_developer_version WHERE id=$1", version_id), package)

    async def create_version(self, project_id, actor, body, raw, manifest, digest):
        try:
            async with self.db.transaction() as conn:
                project = await conn.fetchrow("SELECT * FROM biz_developer_project WHERE id=$1 FOR UPDATE", project_id)
                await _authorize_project(conn, project, actor)
                existing = await conn.fetchrow("SELECT * FROM biz_developer_version WHERE actor=$1 AND request_id=$2", actor, body["request_id"])
                if existing:
                    same = existing["project_id"] == project_id and existing["digest"] == digest
                    same = same and all(existing[key] == body[key] for key in ("channel", "base_version_id", "base_commit"))
                    if not same:
                        raise DuplicateResource("同一请求编号不能提交不同模块包或基线")
                    return _version(existing)
                if body["base_version_id"]:
                    parent = await conn.fetchval("SELECT project_id FROM biz_developer_version WHERE id=$1", body["base_version_id"])
                    if parent != project_id:
                        raise InvalidRequest("基础模块版本不属于本项目")
                latest = await conn.fetchrow("SELECT id FROM biz_developer_version WHERE project_id=$1 AND channel=$2 ORDER BY created_at DESC LIMIT 1", project_id, body["channel"])
                if latest and latest["id"] != body["base_version_id"]:
                    raise DuplicateResource("此渠道已有更新版本，请刷新并以最新版本为基础提交")
                stage = "queued" if project["trusted"] else "awaiting_trust"
                row = await conn.fetchrow("""INSERT INTO biz_developer_version
                    (id,project_id,version,channel,base_version_id,base_commit,digest,actor,request_id,manifest,package,stage)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12) RETURNING *""",
                    uuid4().hex, project_id, manifest["version"], body["channel"], body["base_version_id"], body["base_commit"],
                    digest, actor, body["request_id"], json.dumps(manifest), raw, stage)
                await conn.execute("INSERT INTO biz_module_audit(actor,subject,action,payload) VALUES($1,$2,'upload',$3::jsonb)", actor, project_id, json.dumps({"version_id": row["id"], "digest": digest, "version": manifest["version"]}))
                return _version(row)
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateResource("版本号已存在且不可覆盖，请提高 manifest.version 后提交") from exc

    async def retry(self, version_id, actor, *, internal_worker=False):
        async with self.db.transaction() as conn:
            # Foreign-key checks by a concurrent upload only need KEY SHARE.
            # NO KEY UPDATE prevents a project/version lock-order cycle with it.
            row = await conn.fetchrow("SELECT * FROM biz_developer_version WHERE id=$1 FOR NO KEY UPDATE", version_id)
            if row is None:
                raise ResourceNotFound("模块版本不存在")
            project = await conn.fetchrow("SELECT * FROM biz_developer_project WHERE id=$1 FOR SHARE", row["project_id"])
            await _authorize_project(conn, project, actor, internal_worker=internal_worker)
            if row["status"] in ("queued", "running"):
                return _version(row)
            if row["release_job_id"]:
                state = await conn.fetchval("SELECT status FROM biz_module_release WHERE id=$1", row["release_job_id"])
                if state in ("queued", "running", "succeeded"):
                    raise DuplicateResource("该版本已经发布或正在发布，不能改动其验收记录")
            report = _json(row["report"])
            attempts = report.get("previous_attempts", [])[-4:]
            report.pop("previous_attempts", None)
            snapshot = {"previous_attempts": [*attempts, report]}
            row = await conn.fetchrow("""UPDATE biz_developer_version SET status='queued',stage='queued',lease='',lease_until=NULL,
                candidate_commit='',release_job_id='',report=$2::jsonb,events=events || $3::jsonb,updated_at=now()
                WHERE id=$1 RETURNING *""", version_id, json.dumps(snapshot),
                json.dumps([{"stage": "retry", "message": f"{actor} 发起重新验收"}]))
            return _version(row)

    async def claim(self):
        async with self.db.transaction() as conn:
            row = await conn.fetchrow("""SELECT v.* FROM biz_developer_version v JOIN biz_developer_project p ON p.id=v.project_id
                WHERE p.trusted AND (v.status='queued' OR (v.status='running' AND v.lease_until<now()))
                ORDER BY v.created_at FOR UPDATE OF v SKIP LOCKED LIMIT 1""")
            if not row:
                return None
            lease = uuid4().hex
            value = await conn.fetchrow("UPDATE biz_developer_version SET status='running',stage='claimed',lease=$2,lease_until=now()+interval '90 seconds',updated_at=now() WHERE id=$1 RETURNING *", row["id"], lease)
            return {**_version(value), "lease": lease}

    async def update_version(self, version_id, lease, values):
        event = values.get("event")
        row = await self.db.fetchrow("""UPDATE biz_developer_version v SET status=COALESCE($3,v.status),stage=COALESCE($4,v.stage),
            report=v.report || $5::jsonb,events=v.events || $6::jsonb,candidate_commit=COALESCE($7,v.candidate_commit),
            lease_until=now()+interval '90 seconds',updated_at=now()
            FROM biz_developer_project p WHERE v.id=$1 AND v.lease=$2 AND v.status='running' AND v.lease_until>now()
            AND p.id=v.project_id AND p.trusted RETURNING v.*""", version_id, lease, values.get("status"), values.get("stage"),
            json.dumps(values.get("report", {})), json.dumps([event] if event else []), values.get("candidate_commit"))
        if row is None:
            raise DuplicateResource("验收租约已失效或项目信任已撤销，执行器必须停止")
        return _version(row)

    async def release(self, version_id, actor, expected_revision, *, internal_worker=False):
        try:
            async with self.db.transaction() as conn:
                row = await conn.fetchrow("SELECT * FROM biz_developer_version WHERE id=$1 FOR NO KEY UPDATE", version_id)
                if row is None:
                    raise ResourceNotFound("模块版本不存在")
                project = await conn.fetchrow("SELECT * FROM biz_developer_project WHERE id=$1 FOR SHARE", row["project_id"])
                await _authorize_project(conn, project, actor, internal_worker=internal_worker)
                if not project["trusted"]:
                    raise AccessDenied("项目尚未取得运行授权")
                if internal_worker and (not project["auto_deploy"] or row["channel"] != "main"):
                    raise AccessDenied("自动发布策略已撤销或版本不属于 main 渠道")
                if row["release_job_id"]:
                    return _job(await conn.fetchrow("SELECT * FROM biz_module_release WHERE id=$1", row["release_job_id"]))
                report = _json(row["report"])
                gates = {gate["name"]: gate["status"] for gate in report.get("gates", [])}
                if row["status"] != "passed" or not row["candidate_commit"] or any(gates.get(name) != "passed" for name in ("contracts", "tests", "build", "dataflow")):
                    raise InvalidRequest("必须通过契约、测试、构建和真实数据流验收后才能发布")
                dataflow = report.get("dataflow", {})
                artifacts = dataflow.get("artifacts", {})
                if report.get("rules_version") != "3" or dataflow.get("passed") is not True or artifacts.get("revision") != row["candidate_commit"] or not artifacts.get("api_image") or not artifacts.get("web_image"):
                    raise InvalidRequest("缺少与候选提交绑定的数据流验收及镜像凭证，必须重新验收")
                browser = dataflow.get("browser")
                if not isinstance(browser, dict) or browser.get("passed") is not True or browser.get("revision") != row["candidate_commit"]:
                    raise InvalidRequest("缺少与候选提交绑定的真实浏览器验收，必须重新验收")
                if report.get("release_blockers"):
                    raise InvalidRequest("此版本存在发布阻断：" + "; ".join(report["release_blockers"]))
                if report.get("expected_revision", "") != expected_revision:
                    raise DuplicateResource("环境已有新版本，需要重新装配并验收，避免覆盖其他开发者的修改")
                job_id = uuid4().hex
                result = {"expected_revision": expected_revision, "version_id": version_id, "digest": row["digest"], "rules_version": "3", "accepted_artifacts": artifacts}
                job = await conn.fetchrow("""INSERT INTO biz_module_release
                    (id,commit_sha,kind,actor,request_id,status,result,events) VALUES($1,$2,'deploy',$3,$4,'queued',$5::jsonb,$6::jsonb) RETURNING *""",
                    job_id, row["candidate_commit"], actor, "version-" + version_id, json.dumps(result),
                    json.dumps([{"stage": "approved", "message": "已授权项目的版本通过全部平台门禁，自动进入测试发布队列"}]))
                await conn.execute("UPDATE biz_developer_version SET release_job_id=$2,updated_at=now() WHERE id=$1", version_id, job_id)
                return _job(job)
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateResource("环境正在发布其他版本，此版本保持验收结果并等待重试") from exc

    async def ready(self):
        return [_version(row) for row in await self.db.fetch("""SELECT v.* FROM biz_developer_version v JOIN biz_developer_project p ON p.id=v.project_id
            WHERE v.status='passed' AND v.release_job_id='' AND v.channel='main' AND p.trusted AND p.auto_deploy
            ORDER BY v.created_at LIMIT 30""")]

    async def heartbeat(self, value):
        await self.db.execute("INSERT INTO biz_developer_worker(id,payload) VALUES($1,$2::jsonb) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload,updated_at=now()", value["worker_id"], json.dumps(value))

    async def status(self):
        row = await self.db.fetchrow("SELECT *,updated_at>now()-interval '45 seconds' AS healthy FROM biz_developer_worker ORDER BY updated_at DESC LIMIT 1")
        payload = _json(row["payload"]) if row else {}
        return {"base_commit": payload.get("base_commit", ""),
            "worker": {"last_seen": row["updated_at"].isoformat() if row else None, "healthy": bool(row and row["healthy"]), "rules_version": payload.get("rules_version", "")},
            "environment": {"revision": payload.get("environment_revision", ""), "url": "http://127.0.0.1:5175"},
            "pending_versions": await self.db.fetchval("SELECT count(*) FROM biz_developer_version WHERE status IN ('queued','running')")}
