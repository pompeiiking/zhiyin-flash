"""Planned restart acceptance for existing developer-v2 evidence.

Prepare only until the operator pauses the idle host release/source workers and
authorizes this maintenance. Then pass --execute-restart. The only restarted
containers are the workbench postgres/redis/api and the journal-confirmed staging
active API/background. This is planned downtime, separate from deployment health
continuity. Existing business records are read; no new project, workflow or plan
is created. The original 5173/8000 project is only observed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.request

from module_executor import read_env, request

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / ".platform/acceptance"
WORKBENCH = "http://127.0.0.1:8014"
STAGING = "http://127.0.0.1:5175"
ORIGINAL = "http://127.0.0.1:8000"
WORKBENCH_PROJECT = "zhiyin-module-workbench"
STAGING_PROJECT = "zhiyin-module-staging-bluegreen"

SNAPSHOT_CODE = r'''
import asyncio, hashlib, json, sys
import asyncpg
from zhiyin_boot.settings import Settings
async def main():
    query = json.loads(sys.argv[1])
    db = await asyncpg.connect(Settings.from_env().postgres_dsn)
    output = {}
    async def digest(key, sql, *args):
        rows = await db.fetch(sql, *args)
        values = sorted(row["value"] for row in rows)
        output[key] = {"rows": len(values), "sha256": hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()}
    try:
        async with db.transaction(isolation="repeatable_read", readonly=True):
            await digest("module_policies", "SELECT row_to_json(t)::text AS value FROM biz_module_policy t")
            await digest("runtime_revision_fence", "SELECT row_to_json(t)::text AS value FROM biz_module_runtime_revision t")
            output["active_runtime_revision"] = await db.fetchval("SELECT active_revision FROM biz_module_runtime_revision WHERE id=1")
            if query["environment"] == "workbench":
                pid, workflows = query["project_id"], query["workflow_ids"]
                await digest("project", "SELECT row_to_json(t)::text AS value FROM biz_developer_project t WHERE id=$1", pid)
                await digest("versions_and_packages", "SELECT ((to_jsonb(t)-'package') || jsonb_build_object('package_md5',md5(package)))::text AS value FROM biz_developer_version t WHERE project_id=$1", pid)
                await digest("releases", "SELECT row_to_json(r)::text AS value FROM biz_module_release r WHERE r.result->>'version_id' IN (SELECT id FROM biz_developer_version WHERE project_id=$1)", pid)
                await digest("workflow_drafts", "SELECT row_to_json(t)::text AS value FROM biz_module_workflow t WHERE id=ANY($1::text[])", workflows)
                await digest("published_workflows", "SELECT row_to_json(t)::text AS value FROM biz_module_workflow_version t WHERE workflow_id=ANY($1::text[])", workflows)
                await digest("workflow_runs", "SELECT row_to_json(t)::text AS value FROM biz_module_workflow_run t WHERE workflow_id=ANY($1::text[])", workflows)
                output["active_version_jobs"] = await db.fetchval("SELECT count(*) FROM biz_developer_version v JOIN biz_developer_project p ON p.id=v.project_id WHERE v.status='running' OR (v.status='queued' AND p.trusted)")
                output["active_releases"] = await db.fetchval("SELECT count(*) FROM biz_module_release WHERE status IN ('queued','running')")
            else:
                for table in ("biz_profile", "biz_profile_field", "biz_profile_gap", "biz_asset_version", "biz_asset_content", "biz_user_note", "biz_calendar_node", "biz_track_event"):
                    await digest(table, f"SELECT row_to_json(t)::text AS value FROM {table} t WHERE user_id=$1", query["account"])
        print("PLATFORM_PERSISTENCE_SNAPSHOT=" + json.dumps(output))
    finally:
        await db.close()
asyncio.run(main())
'''


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def run(lifecycle_path, output):
    report = {"passed": False, "planned_maintenance": True, "scope": "restart persistence, separate from release continuity",
        "assertions": [], "restart_operations": [], "business_mutations": [], "started_at": datetime.now(timezone.utc).isoformat()}
    secrets, samples, tokens = [], [], {}
    stop = threading.Event()
    monitor = None
    output.parent.mkdir(parents=True, exist_ok=True)

    def redact(value):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return value

    def save():
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(redact(json.dumps(report, ensure_ascii=False, indent=2)), encoding="utf-8")
        temporary.replace(output)

    def assertion(name, condition, **evidence):
        report["assertions"].append({"id": name, "passed": bool(condition), **evidence})
        save()
        if not condition:
            raise AssertionError(name)

    def docker(*arguments, input=None, timeout=60):
        result = subprocess.run(["docker", *arguments], input=input, text=True, encoding="utf-8", capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(redact(f"Docker command failed ({result.returncode}): {result.stderr}"))
        return result.stdout.strip()

    def inspect(name):
        template = "\n".join(("{{.Id}}", "{{.Image}}", "{{.State.Status}}", "{{.State.StartedAt}}",
            '{{index .Config.Labels "com.docker.compose.project"}}', '{{index .Config.Labels "com.docker.compose.service"}}',
            "{{json .NetworkSettings.Ports}}", '{{with (index .State "Health")}}{{.Status}}{{else}}none{{end}}'))
        value = docker("inspect", "--format", template, name).splitlines()
        if len(value) != 8:
            raise AssertionError("Unexpected container inspection shape")
        return dict(zip(("id", "image", "status", "started_at", "project", "service", "ports", "health"), value, strict=True))

    def api(base, path):
        return request(base, "/api/v1" + path, token=tokens[base], timeout=60)

    def database_snapshot(container, **query):
        text = docker("exec", "-i", container, "python", "-", json.dumps(query), input=SNAPSHOT_CODE)
        lines = [line.removeprefix("PLATFORM_PERSISTENCE_SNAPSHOT=") for line in text.splitlines() if line.startswith("PLATFORM_PERSISTENCE_SNAPSHOT=")]
        if len(lines) != 1:
            raise AssertionError("Missing PostgreSQL snapshot")
        return json.loads(lines[0])

    def wait_health(base, revision, environment=None):
        deadline = time.monotonic() + 180
        last = "not ready"
        while time.monotonic() < deadline:
            try:
                health = request(base, "/healthz", timeout=3)
                if health["status"] == "ok" and health.get("revision") == revision and (environment is None or health.get("environment") == environment):
                    return health
                last = "health, revision or environment mismatch"
            except Exception as exc:
                last = type(exc).__name__
            time.sleep(1)
        raise TimeoutError(f"Service did not recover: {base}: {last}")

    def wait_container(name):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            value = inspect(name)
            if value["status"] == "running" and value["health"] in {"none", "healthy"}:
                return value
            time.sleep(1)
        raise TimeoutError("Container did not recover: " + name)

    def original_web():
        with urllib.request.urlopen("http://127.0.0.1:5173", timeout=10) as response:
            return {"status": response.status, "html_sha256": hashlib.sha256(response.read()).hexdigest()}

    try:
        state = json.loads(lifecycle_path.read_text(encoding="utf-8"))
        mid, revision = state["project_id"], state["installed_revision"]
        assertion("valid_existing_lifecycle", bool(re.fullmatch(r"[a-z][a-z0-9_]{1,47}", mid))
            and bool(re.fullmatch(r"[a-f0-9]{40}", revision)))
        workflow_ids = sorted({entry["workflow_id"] for entry in state["checks"]
            if entry.get("passed") and entry.get("workflow_id") and entry.get("check", "").startswith("published_workflow_")})
        assertion("existing_published_workflow_evidence_available", bool(workflow_ids))
        config = json.loads((ROOT / ".platform/executor.json").read_text(encoding="utf-8"))
        journal_path = Path(config["state_directory"]) / "bluegreen/deployment.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        route = request(STAGING, "/__platform_route")
        assertion("actual_route_matches_active_deployment_journal", route["slot"] in {"blue", "green"}
            and route["slot"] == journal["active_slot"] and route["revision"] == journal["active_revision"] == revision
            and not journal.get("pending"))
        active_api = f"{STAGING_PROJECT}-api_{route['slot']}-1"
        background = f"{STAGING_PROJECT}-background-1"
        wb_api = f"{WORKBENCH_PROJECT}-api-1"
        wb_postgres, wb_redis = (f"{WORKBENCH_PROJECT}-{service}-1" for service in ("postgres", "redis"))
        targets = {wb_postgres: (WORKBENCH_PROJECT, "postgres"), wb_redis: (WORKBENCH_PROJECT, "redis"),
            wb_api: (WORKBENCH_PROJECT, "api"), active_api: (STAGING_PROJECT, "api_" + route["slot"]),
            background: (STAGING_PROJECT, "background")}
        containers_before = {name: inspect(name) for name in targets}
        for name, (project, service) in targets.items():
            actual = containers_before[name]
            ports = json.loads(actual["ports"])
            host_ports = {str(binding["HostPort"]) for bindings in ports.values() for binding in (bindings or [])}
            assertion("restart_target_" + service, actual["project"] == project and actual["service"] == service
                and actual["status"] == "running" and not ({"5173", "8000"} & host_ports), container=name)
        expected_image = journal["slots"][route["slot"]]["api_image"]
        image_id = docker("image", "inspect", "--format", "{{.Id}}", expected_image)
        assertion("active_and_background_use_installed_image", containers_before[active_api]["image"] == image_id
            and containers_before[background]["image"] == image_id)
        original_names = sorted(set(docker("ps", "--filter", "publish=5173", "--format", "{{.Names}}").splitlines()
            + docker("ps", "--filter", "publish=8000", "--format", "{{.Names}}").splitlines()) - {""})
        assertion("original_containers_are_outside_restart_targets", bool(original_names) and not (set(original_names) & set(targets)))
        original_before = {name: inspect(name) for name in original_names}
        original_health = request(ORIGINAL, "/healthz")
        original_html = original_web()
        wb_health = request(WORKBENCH, "/healthz")
        assertion("workbench_and_staging_are_healthy", wb_health["status"] == "ok" and wb_health["environment"] == "workbench"
            and request(STAGING, "/healthz")["revision"] == revision)
        for base, environment in ((WORKBENCH, "workbench"), (STAGING, "staging")):
            values = read_env(ROOT / f".platform/{environment}.env")
            secrets.extend(value for key, value in values.items() if any(word in key for word in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")))
            tokens[base] = request(base, "/api/v1/app/auth/login", body={"account": "admin", "password": values["PLATFORM_ACCOUNT_PASSWORD"]})["token"]
            secrets.append(tokens[base])

        def capture():
            project = next(item for item in api(WORKBENCH, "/developer/projects") if item["id"] == mid)
            versions = api(WORKBENCH, f"/developer/projects/{mid}/versions")
            version_ids = {item["id"] for item in versions}
            releases = [item for item in api(WORKBENCH, "/developer/releases") if item["result"].get("version_id") in version_ids]
            workflows = [item for item in api(WORKBENCH, "/developer/workflows") if item["id"] in workflow_ids]
            runs = {wid: api(WORKBENCH, f"/developer/workflows/{wid}/runs") for wid in workflow_ids}
            installed = api(STAGING, "/developer/modules")
            target = next(item for item in installed if item["manifest"]["id"] == mid)
            return {"api": {
                    "project": digest(project), "versions_reports": digest(versions), "release_reports": digest(releases),
                    "workflow_drafts": digest(workflows), "workflow_runs": digest(runs),
                    "workbench_modules_and_policies": digest(api(WORKBENCH, "/developer/modules")),
                    "staging_modules_and_policies": digest(installed), "core_plan": digest(api(STAGING, "/app/plan/action")),
                    "uploaded_module_result": digest(api(STAGING, f"/app/modules/{mid}/data"))},
                "inventory": {"project": mid, "versions": [{key: item[key] for key in ("id", "version", "status", "candidate_commit")} for item in versions],
                    "releases": [{key: item[key] for key in ("id", "commit", "status")} for item in releases],
                    "workflows": [{key: item[key] for key in ("id", "revision", "published_revision")} for item in workflows],
                    "run_ids": {wid: [item["id"] for item in values] for wid, values in runs.items()},
                    "installed_module": {"id": mid, "version": target["manifest"]["version"], "source_revision": target["source_revision"],
                        "effective_enabled": target["effective_enabled"]}},
                "workbench_db": database_snapshot(wb_api, environment="workbench", project_id=mid, workflow_ids=workflow_ids),
                "staging_db": database_snapshot(active_api, environment="staging", account="admin")}

        before = capture()
        assertion("runtime_fence_matches_installed_build", before["staging_db"]["active_runtime_revision"] == revision
            and before["workbench_db"]["active_runtime_revision"] in {"", wb_health["revision"]})
        assertion("all_existing_evidence_present_before_restart", len(before["inventory"]["versions"]) >= 2
            and any(item["id"] == state["good_version_id"] and item["candidate_commit"] == revision and item["status"] == "passed" for item in before["inventory"]["versions"])
            and any(item["id"] == state["release_job_id"] and item["status"] == "succeeded" for item in before["inventory"]["releases"])
            and len(before["inventory"]["workflows"]) == len(workflow_ids) and before["workbench_db"]["published_workflows"]["rows"] >= len(workflow_ids)
            and all(before["inventory"]["run_ids"].values()) and before["inventory"]["installed_module"]["effective_enabled"])
        assertion("release_and_source_queues_idle", before["workbench_db"]["active_version_jobs"] == 0 and before["workbench_db"]["active_releases"] == 0)
        report.update(project_id=mid, installed_revision=revision, lifecycle=str(lifecycle_path), active_route=route,
            journal=str(journal_path), before=before, containers_before=containers_before, original_containers_before=original_before)
        save()

        def probe_original():
            while not stop.is_set():
                try:
                    value = request(ORIGINAL, "/healthz", timeout=3)
                    samples.append({"ok": value["status"] == "ok" and value.get("revision") == original_health.get("revision")})
                except Exception as exc:
                    samples.append({"ok": False, "error": type(exc).__name__})
                stop.wait(.5)

        def restart(names):
            # No compose down/up or computed project-wide operation: exact names
            # were checked against labels, active journal and published ports.
            assert set(names).issubset(targets)
            report["restart_operations"].append({"containers": names, "started_at": datetime.now(timezone.utc).isoformat()})
            save()
            docker("restart", "--time", "20", *names, timeout=120)
            for name in names:
                wait_container(name)
            report["restart_operations"][-1]["completed_at"] = datetime.now(timezone.utc).isoformat()
            save()

        monitor = threading.Thread(target=probe_original, daemon=True)
        monitor.start()
        restart([wb_postgres, wb_redis])
        restart([wb_api])
        wait_health(WORKBENCH, wb_health["revision"], "workbench")
        restart([active_api, background])
        wait_health(STAGING, revision, "staging")
        after = capture()  # Deliberately reuse the pre-restart JWTs.
        report["after"] = after
        for area in ("api", "inventory", "workbench_db", "staging_db"):
            assertion(area + "_persisted_unchanged", before[area] == after[area])
        containers_after = {name: inspect(name) for name in targets}
        report["containers_after"] = containers_after
        assertion("all_and_only_requested_container_processes_restarted", all(
            containers_after[name]["id"] == old["id"] and containers_after[name]["image"] == old["image"]
            and containers_after[name]["started_at"] != old["started_at"] and containers_after[name]["status"] == "running"
            for name, old in containers_before.items()))
        assertion("bluegreen_route_and_installed_revision_unchanged", request(STAGING, "/__platform_route") == route
            and request(STAGING, "/version.json")["revision"] == revision)
        assertion("original_5173_containers_and_html_unchanged", {name: inspect(name) for name in original_names} == original_before
            and original_web() == original_html and request(ORIGINAL, "/healthz").get("revision") == original_health.get("revision"))
        report["passed"] = True
    except Exception as exc:
        report["error"] = redact(f"{type(exc).__name__}: {exc}")
    finally:
        stop.set()
        if monitor:
            monitor.join(timeout=5)
        report["original_project_health_samples"] = {"count": len(samples), "failures": [sample for sample in samples if not sample["ok"]]}
        if monitor and (not samples or any(not sample["ok"] for sample in samples)):
            report["passed"] = False
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print("ZHIYIN_PLATFORM_PERSISTENCE_REPORT=" + redact(json.dumps(report, ensure_ascii=False)))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle", type=Path, default=DIRECTORY / "developer-v2-lifecycle.json")
    parser.add_argument("--output", type=Path, default=DIRECTORY / "platform-persistence.json")
    parser.add_argument("--execute-restart", action="store_true", help="Execute only after idle host workers were paused and planned maintenance was authorized")
    args = parser.parse_args()
    if not args.execute_restart:
        parser.error("Restart acceptance requires explicit --execute-restart after planned maintenance authorization")
    raise SystemExit(0 if run(args.lifecycle, args.output) else 1)
