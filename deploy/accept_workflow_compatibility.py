"""Opt-in real Docker/PG proof for published workflow upgrade protection.

Run after a platform baseline with publication locks has been installed. Creates
one synthetic account and an ultimately unpublished read-only workflow. It never
runs that workflow, updates the runtime fence, or changes the application route.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
from uuid import uuid4


HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base, bg, helper = (load(name) for name in ("module_executor", "module_bluegreen", "module_workflow_guard"))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main(args):
    require(re.fullmatch(r"[a-z][a-z0-9_]{1,47}", args.module), "Invalid module ID")
    require(bg.IMAGE.fullmatch(args.candidate_image), "Candidate must be an immutable image ID")
    require(bg.REVISION.fullmatch(args.candidate_revision), "Candidate requires a full revision")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    ex = base.Executor(config)
    rollout = bg.BlueGreenRollout(ex)
    suffix = uuid4().hex[:12]
    name, account, flow = "zhiyin-workflow-acceptance-" + suffix, "wf_accept_" + suffix, "wf_accept_" + suffix
    report = {"passed": False, "scope": "real_target_db_readonly_workflow_compatibility",
        "started_at": time.time(), "candidate_image": args.candidate_image, "candidate_revision": args.candidate_revision,
        "synthetic_workflow": flow, "module_id": args.module, "checks": {}, "no_workflow_execution": True, "no_fence_update": True}
    container, token, published, lock = None, "", False, None
    before = None

    def save():
        bg.atomic_json(args.output, report)

    def api(path, body=None):
        require(time.time() - report["started_at"] < 300, "Workflow acceptance time budget exceeded")
        return ex.request(ex.target, "/api/v1" + path, token=token, body=body, timeout=10)

    def publication(operation):
        return api(f"/developer/workflows/{flow}/{operation}", {"expected_revision": 1})

    def runtime_fence():
        code = """import asyncio,os,asyncpg
async def main():
 c=await asyncpg.connect(os.environ['ZHIYIN_POSTGRES_DSN'],timeout=5,command_timeout=5)
 try: print(await c.fetchval('SELECT active_revision FROM biz_module_runtime_revision WHERE id=1'))
 finally: await c.close(timeout=5)
asyncio.run(main())
"""
        return ex.run(["docker", "exec", active_id, "python", "-c", code], timeout=20).strip()

    try:
        before = rollout.reconcile()
        report["route_before"] = before
        require(not rollout.journal.get("pending"), "Do not run while a rollout is pending")
        active_id = rollout.compose("ps", "-q", "api_" + before["slot"]).strip()
        require(re.fullmatch(r"[a-f0-9]{64}", active_id), "Active service container ID is invalid")
        report["fence_before"] = runtime_fence()
        require(report["fence_before"] == before["revision"], "Platform fence baseline is not installed")
        # Keep connection credentials in memory. Executor.run deliberately
        # redacts its output, so its result cannot be reused as configuration.
        inspected = subprocess.run(["docker", "inspect", "--format", "{{json .Config.Env}}", active_id],
            capture_output=True, timeout=10, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        require(inspected.returncode == 0, "Cannot privately inspect active connection settings")
        environment = dict(value.split("=", 1) for value in json.loads(inspected.stdout) if "=" in value)
        require(environment.get("ZHIYIN_MODULE_ENV") == "staging", "Active container is not the staging environment")
        # Only database/cache/identity settings are passed; no model credential.
        selected = {key: value for key, value in environment.items() if key in {
            "ZHIYIN_POSTGRES_DSN", "ZHIYIN_USE_POSTGRES", "ZHIYIN_AUTH_JWT_SECRET", "ZHIYIN_REDIS_URL", "ZHIYIN_USE_REDIS"}}
        selected.update(ZHIYIN_MODULE_ENV="staging", ZHIYIN_ENV="docker", ZHIYIN_RUN_BACKGROUND_WORKERS="0",
                        ZHIYIN_BUILD_REVISION=args.candidate_revision, ZHIYIN_USE_REMOTE_LLM="1", ZHIYIN_LLM_API_KEY="workflow-validation-only")
        ex.secrets.extend(value for key, value in selected.items() if any(part in key for part in ("SECRET", "DSN")))
        image = json.loads(ex.run(["docker", "image", "inspect", args.candidate_image], timeout=10, capture_full=True))[0]
        baked = dict(value.split("=", 1) for value in image["Config"]["Env"] if "=" in value)
        require(image["Id"] == args.candidate_image and baked.get("ZHIYIN_BUILD_REVISION") == args.candidate_revision,
                "Candidate image does not contain the requested revision")
        password = uuid4().hex + uuid4().hex
        ex.secrets.append(password)
        rollout.extra_env["PLATFORM_ACCOUNT_PASSWORD"] = password
        rollout.compose("exec", "-T", "-e", "PLATFORM_ACCOUNT_PASSWORD", "api_" + before["slot"],
                        "python", "scripts/module_admin.py", account, "--role", "admin", "--reset-password")
        token = ex.request(ex.target, "/api/v1/app/auth/login", body={"account": account, "password": password}, timeout=10)["token"]
        ex.secrets.append(token)
        installed = next(item for item in api("/developer/modules") if item["manifest"]["id"] == args.module)
        current_version = installed["manifest"]["version"]
        report["pinned_version"] = current_version
        plan_before = api("/app/plan/action")
        api("/developer/workflows", {"id": flow, "name": "发布兼容性合成验收 " + suffix, "expected_revision": 0,
            "nodes": [{"id": "read_module", "module_id": args.module, "module_version": current_version, "input": json.loads(args.input_json)}]})
        publication("publish")
        published = True
        network = ex.config.get("bluegreen_shared_network", "zhiyin-module-staging_default")
        command = ["docker", "run", "-d", "--name", name, "--network", network, "--entrypoint", "python"]
        for key in selected:
            command.extend(["-e", key])
        command.extend([args.candidate_image, "-c", "import time; time.sleep(600)"])
        container = ex.run(command, extra_env=selected, timeout=30).strip()
        lock = helper.WorkflowPublicationGuard(ex, container)
        rejection = ""
        try:
            lock.acquire()
        except RuntimeError as exc:
            rejection = str(exc)
        finally:
            lock.close()
        require(lock.report is not None and lock.report.get("passed") is False, "Candidate did not reject an incompatible published snapshot")
        failed = [item for item in lock.report["workflows"] if item["workflow_id"] == flow and not item["passed"]]
        require(failed and args.module in rejection and current_version in rejection, "Rejection lacks workflow/module/version evidence")
        report["checks"]["published_pin_blocks_candidate"] = {"passed": True, "report": lock.report, "error": rejection}
        publication("unpublish")
        published = False
        report["checks"]["failure_releases_publication_lock"] = {"passed": True}
        lock = helper.WorkflowPublicationGuard(ex, container)
        report["checks"]["unpublished_dependency_allows_candidate"] = {"passed": True, "report": lock.acquire()}
        blocked = None
        try:
            publication("publish")
            published = True
        except urllib.error.HTTPError as exc:
            blocked = {"http_status": exc.code, "message": json.loads(exc.read()).get("message", "")}
        require(blocked and blocked["http_status"] == 409, "Concurrent publication did not return immediate HTTP 409")
        report["checks"]["publication_blocked_while_guard_held"] = {"passed": True, **blocked}
        lock.close()
        publication("publish")
        published = True
        publication("unpublish")
        published = False
        report["checks"]["success_releases_publication_lock"] = {"passed": True}
        require(api(f"/developer/workflows/{flow}/runs") == [], "Validation unexpectedly executed a workflow")
        require(api("/app/plan/action") == plan_before, "Synthetic business data changed")
        require(rollout.route() == before, "Application route changed during validation")
        report["fence_after"] = runtime_fence()
        require(report["fence_after"] == report["fence_before"], "Runtime revision fence changed")
        report["checks"]["no_execution_or_cutover"] = {"passed": True}
        report["passed"] = True
    except Exception as exc:  # noqa: BLE001 - Persist concrete real acceptance failures.
        report["error"] = ex.redact(str(exc))
    finally:
        if lock:
            lock.close()
        cleanup = []
        if published and token:
            try:
                publication("unpublish")
            except Exception as exc:  # noqa: BLE001
                cleanup.append(ex.redact(str(exc)))
        if container:
            try:
                ex.run(["docker", "rm", "-f", container], timeout=20)
                remaining = ex.run(["docker", "ps", "-aq", "--filter", "name=^/" + name + "$"], timeout=10).strip()
                require(not remaining, "Temporary compatibility container remains")
            except Exception as exc:  # noqa: BLE001
                cleanup.append(ex.redact(str(exc)))
        try:
            report["route_after"] = rollout.route()
            require(before is None or report["route_after"] == before, "Active route changed")
        except Exception as exc:  # noqa: BLE001
            cleanup.append(ex.redact(str(exc)))
        report["cleanup_errors"] = cleanup
        report["passed"] = report["passed"] and not cleanup
        report["finished_at"] = time.time()
        save()
    print(json.dumps({"passed": report["passed"], "output": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--input-json", default="{}")
    parser.add_argument("--output", type=Path, default=HERE.parent / ".platform/acceptance/workflow-compatibility.json")
    raise SystemExit(main(parser.parse_args()))
