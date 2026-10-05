"""Real PostgreSQL authorization races, isolated from existing workbench data.

Copy into the workbench API container and execute with its Python environment:
    python /tmp/accept_developer_concurrency.py --output /tmp/developer-concurrency.json

Uses a randomly named, temporary PostgreSQL schema. Existing public tables,
accounts, tokens and module policies are never changed. The report survives;
all synthetic records are removed with that schema even when an assertion fails.
HTTP assertions execute the actual API controllers through ASGI in this process.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
from uuid import uuid4

import asyncpg
import httpx

from zhiyin_api.app import create_app
from zhiyin_api.controllers.developer_controller import router
from zhiyin_boot.settings import Settings
from zhiyin_business.services.developer import DeveloperPlatform
from zhiyin_business.services.identity import DefaultIdentityService
from zhiyin_business.services.modules import ModulePlatform
from zhiyin_data_sdk.gateways.security import AuthPrincipal
from zhiyin_infrastructure.auth.gateway import JwtAuthGateway
from zhiyin_infrastructure.postgres.developer import PostgresDeveloperRepository
from zhiyin_infrastructure.postgres.modules import PostgresModuleRepository
from zhiyin_infrastructure.postgres.repository import PostgresUserRepository
from zhiyin_infrastructure.postgres.schema.business import DDL as BUSINESS_DDL
from zhiyin_infrastructure.postgres.schema.developer import DDL as DEVELOPER_DDL
from zhiyin_infrastructure.postgres.schema.infrastructure import DDL as INFRA_DDL
from zhiyin_infrastructure.postgres.schema.modules import DDL as MODULE_DDL
from zhiyin_kernel.enums import UserRole
from zhiyin_kernel.errors import AccessDenied, InvalidRequest
from zhiyin_kernel.identity import UserAccount


class Connection:
    """Optional observation hook pauses after PostgreSQL actually acquired a lock."""

    def __init__(self, connection, hook):
        self.connection, self.hook = connection, hook

    async def fetchrow(self, query, *args):
        row = await self.connection.fetchrow(query, *args)
        if self.hook:
            await self.hook(self.connection, query, args)
        return row

    def __getattr__(self, name):
        return getattr(self.connection, name)


class Database:
    def __init__(self, pool):
        self.pool = pool
        self.hook = None

    @asynccontextmanager
    async def transaction(self):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                yield Connection(connection, self.hook)

    async def execute(self, query, *args):
        return await self.pool.execute(query, *args)

    async def fetchrow(self, query, *args):
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query, *args):
        return await self.pool.fetchval(query, *args)

    async def fetch(self, query, *args):
        return await self.pool.fetch(query, *args)


def table_ddl(source, table):
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\s*\(.*?\n\);", source, re.S)
    if not match:
        raise AssertionError(f"Production table DDL not found: {table}")
    return match.group()


async def run(output):
    run_id = uuid4().hex
    schema = f"accept_dev_auth_{run_id}"
    report = {
        "passed": False, "run_id": run_id, "schema": schema,
        "environment": os.environ.get("ZHIYIN_MODULE_ENV", ""),
        "storage": "real PostgreSQL / isolated schema", "http_transport": "actual controllers via in-process ASGI",
        "assertions": [], "cleanup": {"schema_removed": False, "existing_public_data_modified": False},
    }
    control = pool = None
    created = False
    tasks = []

    def assertion(name, condition, **evidence):
        report["assertions"].append({"id": name, "passed": bool(condition), **evidence})
        if not condition:
            raise AssertionError(name)

    async def denied(name, operation, expected_error=AccessDenied):
        try:
            await operation
        except expected_error as exc:
            assertion(name, True, error=str(exc))
        else:
            assertion(name, False)

    try:
        if report["environment"] != "workbench":
            raise RuntimeError("Run only inside the isolated workbench API container")
        settings = Settings.from_env()
        if not settings.use_postgres:
            raise RuntimeError("Real PostgreSQL is required")
        if not re.fullmatch(r"accept_dev_auth_[0-9a-f]{32}", schema):
            raise AssertionError("Invalid generated schema")
        control = await asyncpg.connect(settings.postgres_dsn)
        await control.execute(f'CREATE SCHEMA "{schema}"')
        created = True
        pool = await asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=6,
            server_settings={"search_path": schema, "application_name": f"developer-auth-{run_id[:12]}"})
        db = Database(pool)
        assertion("isolated_search_path", await db.fetchval("SELECT current_schema()") == schema)
        ddl = "\n".join((table_ddl(BUSINESS_DDL, "biz_user_account"),
            table_ddl(INFRA_DDL, "infra_auth_session"), MODULE_DDL, DEVELOPER_DDL))
        await db.execute(ddl)
        await db.execute(ddl)
        assertion("production_ddl_blank_schema_and_repeat", True)
        release_repository = PostgresModuleRepository(db)
        assertion("platform_release_empty_queue_real_sql", await release_repository.claim() is None)
        users = PostgresUserRepository(db)
        auth = JwtAuthGateway(db, secret=secrets.token_hex(32), cache=None)
        identity = DefaultIdentityService(auth, users)
        platform = ModulePlatform(modules={}, repository=None, identity=identity, readers={}, actions={},
            revision="acceptance", environment="workbench", inspect=None, agents=None)
        repository = PostgresDeveloperRepository(db)
        service = DeveloperPlatform(platform, repository, users, None)
        accounts = {key: f"auth_{run_id[:10]}_{key}" for key in ("owner", "member", "demoted")}
        accounts["worker_name"] = "source-worker"
        for uid in accounts.values():
            await users.create(UserAccount(id=uid, nickname="Synthetic authorization acceptance",
                role=UserRole.DEVELOPER, created_at=datetime.now(timezone.utc)))
        report["synthetic_accounts"] = accounts

        async def project(name, member):
            project_id = f"auth_{run_id[:10]}_{name}"
            await repository.create_project({"id": project_id, "name": "Synthetic authorization acceptance", "description": run_id}, accounts["owner"])
            await db.execute("UPDATE biz_developer_project SET members=$2::jsonb WHERE id=$1", project_id, json.dumps([member]))
            return project_id

        async def upload(project_id, actor, *, version="1.0.0", base=None):
            return await repository.create_version(project_id, actor, {
                "request_id": uuid4().hex, "channel": "main", "base_version_id": base, "base_commit": "a" * 40,
            }, b"synthetic inert source", {"id": project_id, "version": version}, uuid4().hex)

        async def count(project_id):
            return await db.fetchval("SELECT count(*) FROM biz_developer_version WHERE project_id=$1", project_id)

        # The exact original race: the API has checked membership, then a second
        # connection commits its revocation before repository transaction entry.
        pid = await project("revoke_first", accounts["member"])
        stale_user = await users.get_by_id(accounts["member"])
        await service.project(pid, stale_user)
        await db.execute("UPDATE biz_developer_project SET members='[]'::jsonb WHERE id=$1", pid)
        await denied("membership_revoke_commits_after_entry_check", upload(pid, stale_user.id))
        assertion("rejected_upload_leaves_no_version", await count(pid) == 0)

        # Reverse order: repository owns the project lock first. The revoker
        # must wait for that authorized transaction; subsequent uploads fail.
        pid = await project("lock_first", accounts["member"])
        locked, proceed, revoker_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}

        async def hold_project(connection, query, args):
            if "SELECT * FROM biz_developer_project" in query and "FOR UPDATE" in query and args == (pid,):
                pids["writer"] = await connection.fetchval("SELECT pg_backend_pid()")
                locked.set()
                await asyncio.wait_for(proceed.wait(), timeout=10)

        async def revoke_membership():
            async with pool.acquire() as connection:
                pids["revoker"] = await connection.fetchval("SELECT pg_backend_pid()")
                revoker_started.set()
                await connection.execute("UPDATE biz_developer_project SET members='[]'::jsonb WHERE id=$1", pid)

        db.hook = hold_project
        writer = asyncio.create_task(upload(pid, accounts["member"]))
        tasks.append(writer)
        await asyncio.wait_for(locked.wait(), timeout=10)
        revoker = asyncio.create_task(revoke_membership())
        tasks.append(revoker)
        await asyncio.wait_for(revoker_started.wait(), timeout=10)
        blockers = []
        for _ in range(250):
            blockers = await control.fetchval("SELECT pg_blocking_pids($1)", pids["revoker"])
            if pids["writer"] in blockers:
                break
            await asyncio.sleep(0.02)
        assertion("project_lock_blocks_concurrent_membership_revoke", pids["writer"] in blockers and not revoker.done(), blocker_count=len(blockers))
        proceed.set()
        accepted = await asyncio.wait_for(writer, timeout=10)
        await asyncio.wait_for(revoker, timeout=10)
        db.hook = None
        assertion("authorized_write_commits_before_waiting_revoke", await count(pid) == 1, version_id=accepted["id"])
        await denied("later_write_rechecks_committed_membership_revoke",
            upload(pid, accounts["member"], version="1.0.1", base=accepted["id"]))
        assertion("later_denial_creates_no_extra_version", await count(pid) == 1)

        # A real JWT keeps its developer claim, while the authoritative account
        # is downgraded. Test both actual API entry points and the repository
        # after an already-completed entry check.
        pid = await project("demotion", accounts["demoted"])
        version = await upload(pid, accounts["demoted"])
        token = await auth.issue_token(AuthPrincipal(user_id=accounts["demoted"], role=UserRole.DEVELOPER))
        await service.require(token)
        await db.execute("UPDATE biz_user_account SET payload=jsonb_set(payload,'{role}','\"student\"'::jsonb) WHERE id=$1", accounts["demoted"])
        assertion("old_jwt_still_carries_developer_claim", (await auth.authenticate({"token": token})).role == UserRole.DEVELOPER)
        app = create_app(routers=[router])
        app.state.developer_platform = service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic.invalid",
                headers={"Authorization": f"Bearer {token}"}) as client:
            requests = {
                "upload": (f"/developer/projects/{pid}/versions", {"package_base64": "c3ludGhldGlj", "base_commit": "a" * 40, "request_id": uuid4().hex}),
                "retry": (f"/developer/versions/{version['id']}/retry", None),
                "release": (f"/developer/versions/{version['id']}/release", None),
            }
            for operation, (path, body) in requests.items():
                response = await client.post("/api/v1" + path, json=body)
                result = response.json()
                assertion(f"old_token_{operation}_denied_after_role_demotion", response.status_code == 401 and result.get("code") == 1004,
                    http_status=response.status_code, code=result.get("code"))
        await denied("repository_upload_rechecks_demoted_role", upload(pid, accounts["demoted"], version="1.0.1", base=version["id"]))
        await denied("repository_retry_rechecks_demoted_role", repository.retry(version["id"], accounts["demoted"]))
        await denied("repository_release_rechecks_demoted_role", repository.release(version["id"], accounts["demoted"], ""))
        assertion("demotion_does_not_resurrect_role_from_token", (await users.get_by_id(accounts["demoted"])).role == UserRole.STUDENT)
        assertion("demotion_denials_preserve_version", await count(pid) == 1 and (await repository.version(version["id"]))["status"] == "queued")

        # The explicit internal_worker flag is not inferred from an account ID.
        pid = await project("worker_name", accounts["member"])
        version = await upload(pid, accounts["member"])
        await denied("source_worker_named_user_cannot_upload", upload(pid, "source-worker", version="1.0.1", base=version["id"]))
        await denied("source_worker_named_user_cannot_retry", repository.retry(version["id"], "source-worker"))
        await denied("source_worker_named_user_cannot_release", repository.release(version["id"], "source-worker", ""))
        assertion("source_worker_name_does_not_create_release", await db.fetchval("SELECT count(*) FROM biz_module_release") == 0)
        assertion("source_worker_name_does_not_create_version", await count(pid) == 1)
        job_id = uuid4().hex
        await db.execute("""INSERT INTO biz_module_release
            (id,commit_sha,kind,actor,request_id,status,result) VALUES($1,$2,'deploy',$3,$4,'queued',$5::jsonb)""",
            job_id, "b" * 40, accounts["member"], uuid4().hex, json.dumps({"version_id": version["id"]}))
        await db.execute("UPDATE biz_developer_project SET trusted=false WHERE id=$1", pid)
        assertion("revoked_project_queued_release_is_not_claimed", await release_repository.claim() is None)
        cancelled = await db.fetchrow("SELECT status,stage,events FROM biz_module_release WHERE id=$1", job_id)
        events = json.loads(cancelled["events"]) if isinstance(cancelled["events"], str) else cancelled["events"]
        assertion("revoked_project_queued_release_cancelled_with_event", cancelled["status"] == "failed"
            and cancelled["stage"] == "authorization_revoked"
            and any(event.get("stage") == "authorization_revoked" for event in events),
            release_job_id=job_id, status=cancelled["status"], stage=cancelled["stage"])
        pid = await project("browser_attestation", accounts["member"])
        version = await upload(pid, accounts["member"])
        candidate = "c" * 40
        browser = {"gate": "browser", "rules_version": "1", "passed": True, "revision": candidate,
            "no_api_mocking": True, "errors": [], "network_failures": [], "modules": {
                pid: {"version": "1.0.0", "kind": "hybrid", "passed": True, "checks": [
                    {"fixture": fixture, "viewport": viewport, "passed": True}
                    for fixture in ("normal", "empty", "error") for viewport in ("desktop", "narrow")]}}}
        accepted_report = {"rules_version": "3", "expected_revision": "installed",
            "gates": [{"name": name, "status": "passed"} for name in ("contracts", "tests", "build", "dataflow")],
            "dataflow": {"passed": True, "browser": browser, "artifacts": {"revision": candidate,
                "api_image": "synthetic-api@sha256:" + "a" * 64, "web_image": "synthetic-web@sha256:" + "b" * 64}}}
        await db.execute("UPDATE biz_developer_project SET trusted=true WHERE id=$1", pid)
        for defect in ("legacy_rules", "missing_browser", "wrong_browser_revision"):
            defective = json.loads(json.dumps(accepted_report))
            if defect == "legacy_rules":
                defective["rules_version"] = "2"
            elif defect == "missing_browser":
                defective["dataflow"].pop("browser")
            else:
                defective["dataflow"]["browser"]["revision"] = "d" * 40
            await db.execute("UPDATE biz_developer_version SET status='passed',candidate_commit=$2,report=$3::jsonb WHERE id=$1",
                version["id"], candidate, json.dumps(defective))
            await denied(f"release_rejects_{defect}", repository.release(version["id"], accounts["member"], "installed"), InvalidRequest)
            assertion(f"{defect}_does_not_queue_release", await db.fetchval(
                "SELECT count(*) FROM biz_module_release WHERE result->>'version_id'=$1", version["id"]) == 0)
        await db.execute("UPDATE biz_developer_version SET report=$2::jsonb WHERE id=$1", version["id"], json.dumps(accepted_report))
        accepted = await repository.release(version["id"], accounts["member"], "installed")
        assertion("current_browser_attestation_queues_rules_three_release", accepted["status"] == "queued"
            and accepted["result"]["rules_version"] == "3"
            and accepted["result"]["accepted_artifacts"] == accepted_report["dataflow"]["artifacts"])
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if pool:
                await asyncio.wait_for(pool.close(), timeout=10)
            if control and created:
                await control.execute(f'DROP SCHEMA "{schema}" CASCADE')
                report["cleanup"]["schema_removed"] = not await control.fetchval("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=$1)", schema)
        except Exception as exc:
            report["cleanup"]["error"] = f"{type(exc).__name__}: {exc}"
            report["passed"] = False
        finally:
            if control:
                await control.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        if output:
            Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("ZHIYIN_DEVELOPER_CONCURRENCY_REPORT=" + json.dumps(report, ensure_ascii=False))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(options.output)) else 1)
