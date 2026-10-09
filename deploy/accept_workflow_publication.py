"""Real PostgreSQL publication locks and runtime fencing in a disposable schema.

Run inside the workbench API only, after its lock-aware build is installed.
This briefly takes the real workbench advisory publication lock; coordinate the
planned check with deployment activity. No public-schema business data changes.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

import asyncpg

from zhiyin_boot.settings import Settings
from zhiyin_infrastructure.postgres.module_flows import PostgresModuleFlowRepository, WORKFLOW_PUBLICATION_LOCK
from zhiyin_infrastructure.postgres.schema.module_flows import DDL
from zhiyin_kernel.errors import DuplicateResource, ResourceNotFound


class Connection:
    def __init__(self, connection, db):
        self.connection, self.db = connection, db

    async def fetchrow(self, sql, *args):
        result = await self.connection.fetchrow(sql, *args)
        if self.db.pause and "FROM biz_module_workflow WHERE" in sql and "FOR UPDATE" in sql:
            self.db.held.set()
            await self.db.resume.wait()
        return result

    def __getattr__(self, name):
        return getattr(self.connection, name)


class Database:
    def __init__(self, pool):
        self.pool = pool
        self.pause = False
        self.held, self.resume = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def transaction(self):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                yield Connection(connection, self)

    def __getattr__(self, name):
        return getattr(self.pool, name)


async def run(output):
    run_id = uuid4().hex
    schema = f"accept_workflow_{run_id}"
    report = {"passed": False, "run_id": run_id, "schema": schema,
        "storage": "real PostgreSQL / isolated schema", "lock_key": WORKFLOW_PUBLICATION_LOCK,
        "assertions": [], "cleanup": {"schema_removed": False, "public_business_data_modified": False}}
    control = pool = task = None
    created = exclusive = False

    def check(name, passed, **evidence):
        report["assertions"].append({"id": name, "passed": bool(passed), **evidence})
        if not passed:
            raise AssertionError(name)

    async def denied(name, operation, error=DuplicateResource):
        try:
            await asyncio.wait_for(operation, timeout=1)
        except error as exc:
            check(name, True, error=str(exc))
        else:
            check(name, False)

    try:
        if os.environ.get("ZHIYIN_MODULE_ENV") != "workbench":
            raise RuntimeError("Only run in the isolated workbench API")
        report["build_revision"] = os.environ.get("ZHIYIN_BUILD_REVISION", "")
        control = await asyncpg.connect(Settings.from_env().postgres_dsn)
        await control.execute(f'CREATE SCHEMA "{schema}"')
        created = True
        await control.execute(f'SET search_path TO "{schema}"')
        pool = await asyncpg.create_pool(Settings.from_env().postgres_dsn, min_size=1, max_size=4,
            server_settings={"search_path": schema, "application_name": f"workflow-guard-{run_id[:12]}"})
        db = Database(pool)
        await db.execute(DDL)
        await db.execute(DDL)
        check("ddl_idempotent_legacy_empty", await db.fetchval("SELECT active_revision FROM biz_module_runtime_revision WHERE id=1") == "")
        old = PostgresModuleFlowRepository(db, revision="old-build")
        current = PostgresModuleFlowRepository(db, revision="current-build")
        definition = {"input_schema": {}, "nodes": []}
        draft = {"id": "synthetic_flow", "name": "Synthetic flow", "expected_revision": 0, **definition}
        await old.save(draft, "synthetic_owner")
        published = await old.publish(draft["id"], 1, definition, "synthetic_owner")
        check("legacy_empty_allows_first_publication", published["published_revision"] == 1)

        exclusive = await control.fetchval("SELECT pg_try_advisory_lock($1)", WORKFLOW_PUBLICATION_LOCK)
        check("exclusive_deployment_lock_available", exclusive)
        await denied("publication_conflict_rejected_without_wait", old.publish(draft["id"], 1, definition, "synthetic_owner"))
        await denied("unpublication_conflict_rejected_without_wait", old.unpublish(draft["id"], 1, "synthetic_owner"))
        saved = await asyncio.wait_for(old.save({**draft, "expected_revision": 1}, "synthetic_owner"), 1)
        check("draft_save_works_during_deployment", saved["revision"] == 2 and saved["published_revision"] == 1)
        check("exclusive_conflicts_leave_snapshots", await db.fetchval("SELECT count(*) FROM biz_module_workflow_version") == 1)
        await control.fetchval("SELECT pg_advisory_unlock($1)", WORKFLOW_PUBLICATION_LOCK)
        exclusive = False

        db.pause = True
        task = asyncio.create_task(old.publish(draft["id"], 2, definition, "synthetic_owner"))
        await asyncio.wait_for(db.held.wait(), 2)
        exclusive = await control.fetchval("SELECT pg_try_advisory_lock($1)", WORKFLOW_PUBLICATION_LOCK)
        check("real_repository_transaction_blocks_exclusive_deployment", exclusive is False)
        db.resume.set()
        await asyncio.wait_for(task, 2)
        task = None
        db.pause = False
        exclusive = await control.fetchval("SELECT pg_try_advisory_lock($1)", WORKFLOW_PUBLICATION_LOCK)
        check("publication_commit_releases_shared_lock", exclusive)
        await control.execute("UPDATE biz_module_runtime_revision SET active_revision='current-build',updated_at=now() WHERE id=1")
        await control.fetchval("SELECT pg_advisory_unlock($1)", WORKFLOW_PUBLICATION_LOCK)
        exclusive = False
        await denied("stale_api_publish_rejected_after_cutover", old.publish(draft["id"], 2, definition, "synthetic_owner"))
        await denied("stale_api_unpublish_rejected_after_cutover", old.unpublish(draft["id"], 2, "synthetic_owner"))
        await db.execute(DDL)
        check("startup_ddl_preserves_runtime_fence", await db.fetchval("SELECT active_revision FROM biz_module_runtime_revision WHERE id=1") == "current-build")
        await denied("stale_cas_cannot_unpublish", current.unpublish(draft["id"], 1, "synthetic_owner"))
        check("stale_cas_preserves_pointer", (await current.get(draft["id"]))["published_revision"] == 2)
        run, _ = await current.begin_run(draft["id"], 2, "synthetic_user", "synthetic_receipt", "digest", "live")
        run.update(status="succeeded")
        await current.update_run(run)
        paused = await current.unpublish(draft["id"], 2, "synthetic_owner")
        check("current_build_unpublishes_without_draft_change", paused["published_revision"] is None and paused["revision"] == 2 and paused["definition"] == definition)
        await denied("paused_public_read_not_found", current.get(draft["id"], published=True), ResourceNotFound)
        check("unpublish_retains_both_history_snapshots", await db.fetchval("SELECT count(*) FROM biz_module_workflow_version") == 2)
        check("unpublish_retains_execution_receipt", (await current.runs(draft["id"], "synthetic_user")) == [run])
        await current.publish(draft["id"], 2, definition, "synthetic_owner")
        check("same_snapshot_republish_works", (await current.get(draft["id"], published=True))["revision"] == 2)
        await denied("immutable_snapshot_cannot_be_replaced", current.publish(draft["id"], 2, {**definition, "input_schema": {"type": "object"}}, "synthetic_owner"))
        exclusive = await control.fetchval("SELECT pg_try_advisory_lock($1)", WORKFLOW_PUBLICATION_LOCK)
        check("failed_transaction_releases_shared_lock", exclusive)
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if control is not None:
            if exclusive:
                await control.fetchval("SELECT pg_advisory_unlock($1)", WORKFLOW_PUBLICATION_LOCK)
            if pool is not None:
                await pool.close()
            if created:
                await control.execute(f'DROP SCHEMA "{schema}" CASCADE')
                report["cleanup"]["schema_removed"] = True
            await control.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        if output:
            Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("ZHIYIN_WORKFLOW_PUBLICATION_REPORT=" + json.dumps(report, ensure_ascii=False))
    return report["passed"] and report["cleanup"]["schema_removed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(arguments.output)) else 1)
