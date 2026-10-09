"""Validate a newly uploaded ZIP module through the staging Qwen conversation.

Run only after developer lifecycle monitor + verify have completed. The script
creates a fresh student account, temporarily isolates module tool grants, and
restores every changed policy. Its account/conversation remain as marked synthetic
evidence. No existing user's plan is changed. Only ports 5175 and 8014 are used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from module_executor import read_env, request

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / ".platform/acceptance"
STAGING = "http://127.0.0.1:5175"
WORKBENCH = "http://127.0.0.1:8014"
POLICY_FIELDS = ("enabled", "reads", "actions", "agents")

# Read-only, user-scoped business fingerprints. Conversation/session/memory and
# authentication records are intentionally outside the business-write assertion.
SNAPSHOT_CODE = r'''
import asyncio, hashlib, json, os, sys
from urllib.parse import urlsplit
import asyncpg
from zhiyin_boot.settings import Settings
TABLES = ("biz_profile", "biz_profile_field", "biz_profile_gap", "biz_asset_version",
          "biz_asset_content", "biz_user_note", "biz_academic_snapshot", "biz_calendar_node", "biz_track_event")
async def main():
    db = await asyncpg.connect(Settings.from_env().postgres_dsn)
    try:
        result = {"business": {}, "revision": os.environ.get("ZHIYIN_BUILD_REVISION", ""),
                  "remote_llm": os.environ.get("ZHIYIN_USE_REMOTE_LLM", "")}
        async with db.transaction(isolation="repeatable_read", readonly=True):
            for table in TABLES:
                rows = await db.fetch(f"SELECT row_to_json(t)::text AS value FROM {table} t WHERE user_id=$1", sys.argv[1])
                encoded = json.dumps(sorted(row["value"] for row in rows), ensure_ascii=False).encode()
                result["business"][table] = {"rows": len(rows), "sha256": hashlib.sha256(encoded).hexdigest()}
            route = await db.fetchrow("""SELECT r.provider_code,r.model_code,p.protocol,p.base_url FROM infra_ai_route r
                JOIN infra_ai_provider p ON p.code=r.provider_code
                JOIN infra_ai_model m ON m.provider_code=r.provider_code AND m.model_code=r.model_code
                WHERE r.scene='llm' AND r.enabled AND p.enabled AND m.enabled ORDER BY r.priority LIMIT 1""")
            result["active_llm_route"] = dict(route) if route else None
            if result["active_llm_route"]:
                # Provider labels can predate a routing change. Record only the
                # actual hostname, never endpoint credentials or query strings.
                endpoint = urlsplit(result["active_llm_route"].pop("base_url"))
                result["active_llm_route"].update(endpoint_host=endpoint.hostname, endpoint_scheme=endpoint.scheme)
        print("MODEL_ACCEPTANCE_SNAPSHOT=" + json.dumps(result))
    finally:
        await db.close()
asyncio.run(main())
'''


def fields(policy):
    return {key: policy[key] for key in POLICY_FIELDS}


def run(lifecycle_path, output):
    report = {"passed": False, "run_id": uuid4().hex, "assertions": [], "restoration_errors": [],
        "synthetic_data": "Fresh student account and conversation retained as acceptance evidence",
        "read_only_scope": "plan/profile/asset versions/notes/academic/calendar/track; normal chat history and memory persist"}
    originals, attempted = {}, {}
    admin_token = ""
    secrets = []
    output.parent.mkdir(parents=True, exist_ok=True)

    def redact(text):
        for value in secrets:
            if value:
                text = text.replace(value, "[redacted]")
        return text

    def save():
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(redact(json.dumps(report, ensure_ascii=False, indent=2)), encoding="utf-8")
        temporary.replace(output)

    def assertion(name, condition, **evidence):
        report["assertions"].append({"id": name, "passed": bool(condition), **evidence})
        save()
        if not condition:
            raise AssertionError(name)

    def admin(path, body=None, method=None):
        return request(STAGING, "/api/v1" + path, token=admin_token, body=body, method=method, timeout=60)

    def listing():
        return {item["manifest"]["id"]: item for item in admin("/developer/modules")}

    def configure(mid, policy):
        current = listing()[mid]["policy"]
        return admin(f"/developer/modules/{mid}/policy", {**fields(policy), "revision": current["revision"]}, "PUT")

    def docker(container, arguments, *, input=None, environment=None, timeout=60):
        command = ["docker", "exec"]
        if input is not None:
            command.append("-i")
        for key in environment or {}:
            command.extend(["-e", key])
        command.extend([container, *arguments])
        result = subprocess.run(command, input=input, text=True, encoding="utf-8", capture_output=True,
            timeout=timeout, env={**os.environ, **(environment or {})})
        if result.returncode:
            raise RuntimeError(redact(f"Container command failed ({result.returncode}): {result.stdout}\n{result.stderr}"))
        return result.stdout

    def snapshot(container, account):
        value = docker(container, ["python", "-", account], input=SNAPSHOT_CODE)
        lines = [line.removeprefix("MODEL_ACCEPTANCE_SNAPSHOT=") for line in value.splitlines() if line.startswith("MODEL_ACCEPTANCE_SNAPSHOT=")]
        if len(lines) != 1:
            raise AssertionError("Missing read-only database snapshot")
        return json.loads(lines[0])

    try:
        state = json.loads(lifecycle_path.read_text(encoding="utf-8"))
        mid, revision, version_id = state["project_id"], state["installed_revision"], state["good_version_id"]
        expected_version = state.get("expected_version", "0.1.1")
        assertion("lifecycle_identifies_new_uploaded_module", bool(re.fullmatch(r"[a-z][a-z0-9_]{1,47}", mid))
            and mid not in {"action_progress", "achievements", "plan_progress_skill"}
            and bool(re.fullmatch(r"[a-f0-9]{40}", revision)) and bool(re.fullmatch(r"[a-f0-9]{32}", version_id)))
        report.update(module_id=mid, installed_revision=revision, uploaded_version_id=version_id, expected_version=expected_version)
        staging_env = read_env(ROOT / ".platform/staging.env")
        workbench_env = read_env(ROOT / ".platform/workbench.env")
        secrets.extend(value for env in (staging_env, workbench_env) for key, value in env.items()
            if any(word in key for word in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")))
        password = staging_env["PLATFORM_ACCOUNT_PASSWORD"]
        admin_token = request(STAGING, "/api/v1/app/auth/login", body={"account": "admin", "password": password})["token"]
        secrets.append(admin_token)
        workbench_token = request(WORKBENCH, "/api/v1/app/auth/login", body={"account": "admin", "password": workbench_env["PLATFORM_ACCOUNT_PASSWORD"]})["token"]
        secrets.append(workbench_token)
        uploaded = request(WORKBENCH, f"/api/v1/developer/versions/{version_id}", token=workbench_token)
        assertion("uploaded_zip_passed_and_matches_deployed_commit", uploaded["project_id"] == mid
            and uploaded["version"] == expected_version and uploaded["status"] == "passed"
            and uploaded["candidate_commit"] == revision and bool(uploaded["release_job_id"]))
        report["uploaded_source"] = {key: uploaded[key] for key in ("id", "project_id", "version", "digest", "candidate_commit", "release_job_id")}
        health = request(STAGING, "/healthz")
        route = request(STAGING, "/__platform_route")
        assertion("public_staging_runs_exact_uploaded_revision", health["environment"] == "staging"
            and health["revision"] == revision and route["revision"] == revision and route["slot"] in {"blue", "green"}
            and request(STAGING, "/version.json")["revision"] == revision)
        container = f"zhiyin-module-staging-bluegreen-api_{route['slot']}-1"
        report.update(route=route, container=container)
        modules = listing()
        module = modules[mid]
        manifest = module["manifest"]
        assertion("new_hybrid_module_has_card_and_registered_tool", manifest["kind"] == "hybrid"
            and bool(manifest["card"]) and bool(manifest["conversation"]) and manifest["tool"] == f"{mid}.read"
            and manifest["version"] == uploaded["version"] and module["source_revision"] == revision)
        assertion("root_verify_authorized_live_module", module["effective_enabled"]
            and set(manifest["reads"]).issubset(module["policy"]["reads"]))
        report.update(manifest=manifest, tool_name=f"module_{mid}_read")
        account = "uploaded_model_" + report["run_id"][:12]
        report["synthetic_account"] = account
        save()
        docker(container, ["python", "scripts/module_admin.py", account, "--role", "student", "--seed"],
            environment={"PLATFORM_ACCOUNT_PASSWORD": password})
        login = request(STAGING, "/api/v1/app/auth/login", body={"account": account, "password": password})
        secrets.append(login["token"])
        assertion("synthetic_account_has_only_student_role", login["role"] == "student")

        def api(path, body=None):
            return request(STAGING, "/api/v1" + path, token=login["token"], body=body, timeout=180)

        # Save recovery material before the first policy mutation. Refresh CAS
        # revisions on restoration; do not overwrite an unrelated concurrent edit.
        originals = {key: value["policy"] for key, value in modules.items()}
        report["original_policies"] = originals
        agent_ids = [agent["id"] for agent in admin("/developer/context")["agents"]]
        assertion("registered_agents_available", bool(agent_ids))
        for key, original in originals.items():
            desired = {**original, "agents": agent_ids if key == mid else []}
            if fields(desired) != fields(original):
                attempted[key] = desired
                report["temporary_policies"] = attempted
                save()
                configure(key, desired)
        effective = listing()
        assertion("only_uploaded_module_has_agent_grants", set(effective[mid]["policy"]["agents"]) == set(agent_ids)
            and all(not item["policy"]["agents"] for key, item in effective.items() if key != mid))
        expected = api(f"/app/modules/{mid}/invoke", {"input": {}, "expected_version": manifest["version"]})
        plan_before = api("/app/plan/action")
        tasks = [{"task_id": task["task_id"], "text": task["text"], "phase": phase["name"], "done": task["done"]}
            for phase in plan_before["phases"] for task in phase["tasks"]]
        assertion("uploaded_module_reads_synthetic_core_plan", expected["data"]["tasks"] == tasks
            and expected["data"]["total"] == len(tasks) == 2 and expected["data"]["completed"] == sum(task["done"] for task in tasks) == 1
            and any(item.get("capability") == "plan.read" and item.get("status") == "succeeded" for item in expected["trace"]))
        session = api("/app/task/enter", {"task_code": "how_to_act"})
        report["task_id"] = session["task_id"]
        before = snapshot(container, account)
        report.update(database_before=before, expected_module_result=expected, plan_before=plan_before)
        model = before.get("active_llm_route") or {}
        assertion("live_qwen_route_and_remote_engine", before["revision"] == revision
            and before["remote_llm"] == "1" and model.get("model_code", "").startswith("qwen")
            and model.get("protocol") == "openai_chat" and model.get("endpoint_scheme") == "https"
            and model.get("endpoint_host") in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"})
        body = {"task_id": session["task_id"], "client_msg_id": "uploaded_model_" + uuid4().hex,
            "message": f"请调用新上传的【{manifest['name']}】模块工具 module_{mid}_read（模块编号 {mid}，工具登记名 {manifest['tool']}），"
                "读取我已经保存的行动计划，展示这个模块的进度卡，告诉我总任务数和已完成数。"
                "必须调用这个指定工具，不能只口头回答；不创建、不修改、不完成任何计划或任务。"}
        report["request"] = body
        save()
        started = time.monotonic()
        reply = api("/app/conversation/message", body)
        report.update(reply=reply, conversation_seconds=round(time.monotonic() - started, 3))
        cards = [item for message in reply["messages"] for item in message.get("renderables", []) if item["kind"] == f"module.{mid}"]
        assertion("qwen_invoked_new_zip_module_and_returned_card", bool(cards)
            and all(card["payload"] == expected for card in cards), card_kind=f"module.{mid}", card_count=len(cards))
        assertion("conversation_did_not_write_assets", not reply["changed_assets"] and api("/app/plan/action") == plan_before)
        history = api(f"/app/sessions/{session['task_id']}/turns")
        report["history"] = history
        persisted = [item for message in history for item in message.get("renderables", []) if item["kind"] == f"module.{mid}"]
        assertion("uploaded_module_card_persisted_in_history", bool(persisted) and all(item["payload"] == expected for item in persisted))
        replay = api("/app/conversation/message", body)
        report["replay"] = replay
        assertion("same_request_replays_identical_messages", replay["messages"] == reply["messages"] and not replay["changed_assets"])
        assertion("retry_does_not_append_conversation_turns", api(f"/app/sessions/{session['task_id']}/turns") == history)
        after = snapshot(container, account)
        report["database_after"] = after
        assertion("query_and_retry_preserve_business_records", before["business"] == after["business"]
            and api("/app/plan/action") == plan_before and api(f"/app/modules/{mid}/data") == expected)
        assertion("staging_revision_stayed_pinned", request(STAGING, "/healthz")["revision"] == revision
            and request(STAGING, "/__platform_route")["revision"] == revision)
        report["passed"] = True
    except Exception as exc:
        report["error"] = redact(f"{type(exc).__name__}: {exc}")
    finally:
        restored = {}
        for mid in reversed(attempted):
            try:
                current = listing()[mid]["policy"]
                if fields(current) not in (fields(originals[mid]), fields(attempted[mid])):
                    raise RuntimeError("Policy was changed concurrently; refused to overwrite another operator's update")
                if fields(current) != fields(originals[mid]):
                    configure(mid, originals[mid])
                current = listing()[mid]["policy"]
                if fields(current) != fields(originals[mid]):
                    raise AssertionError("Restored policy does not match its original values")
                restored[mid] = fields(current)
            except Exception as exc:
                report["restoration_errors"].append(redact(f"{mid}: {type(exc).__name__}: {exc}"))
        report["restored_policies"] = restored
        report["policies_restored"] = not report["restoration_errors"]
        if report["restoration_errors"]:
            report["passed"] = False
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print("ZHIYIN_UPLOADED_MODULE_MODEL_REPORT=" + redact(json.dumps(report, ensure_ascii=False)))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle", type=Path, default=DIRECTORY / "developer-v2-lifecycle.json")
    parser.add_argument("--output", type=Path, default=DIRECTORY / "uploaded-module-model.json")
    arguments = parser.parse_args()
    raise SystemExit(0 if run(arguments.lifecycle, arguments.output) else 1)
