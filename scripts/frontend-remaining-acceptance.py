"""HTTP acceptance in a disposable DB/container, never the user's running DB.

Run inside the isolated API container with /results mounted to the evidence folder.
Synthetic records are setup only; all assertions use real HTTP and PostgreSQL.
No source worker/executor is started and no release is deployed.
"""

import asyncio
import sys
import base64
import datetime
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
from zhiyin_boot.container import build_container
from zhiyin_boot.settings import Settings
from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask, DirectionPlan
from zhiyin_kernel.blackboard import ProfileGap
from zhiyin_kernel.enums import UserRole


async def main():
    settings = Settings.from_env()
    if (
        os.environ.get("ZHIYIN_DATAFLOW_ISOLATED") != "1"
        or os.environ.get("ZHIYIN_MODULE_ENV") != "workbench"
        or "@db:5432/acceptance" not in settings.postgres_dsn
    ):
        raise RuntimeError(
            "Refusing to seed an environment other than the disposable acceptance DB"
        )
    c = build_container(settings)
    suffix = uuid4().hex[:10]
    accounts = {r: f"qa_{r}_{suffix}" for r in ["student", "admin", "other"]}
    password = uuid4().hex
    report = {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "environment": "isolated PostgreSQL + Redis + real HTTP; synthetic account data",
        "results": {},
        "scenarios": {},
        "limitations": [],
    }
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    if only:
        report = json.loads(
            Path("/results/remaining-acceptance-results.json").read_text()
        )
        report["at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    clients = {}

    async def request(
        actor,
        method,
        path,
        *,
        endpoint=None,
        label="success",
        reject=False,
        binary=False,
        **kwargs,
    ):
        key = method + " /api/v1" + (endpoint or path)
        entry = report["results"].setdefault(key, {"cases": []})
        response = await clients[actor].request(method, "/api/v1" + path, **kwargs)
        data = {} if binary else response.json()
        ok = (
            response.is_success
            if binary
            else response.is_success and data.get("code") == 0
        )
        passed = not ok and response.status_code < 500 if reject else ok
        entry["cases"].append(
            {
                "label": label,
                "http": response.status_code,
                "code": data.get("code"),
                "passed": passed,
                "positive": not reject,
                "message": data.get("message", "") if not passed or reject else "ok",
            }
        )
        print(key, label, passed, flush=True)
        if not passed:
            raise AssertionError(
                f"{key}: HTTP {response.status_code}; {data.get('message', '')}"
            )
        return response.content if binary else data.get("data")

    async def stream(path, endpoint, *, arg="", valid=True):
        key = "POST /api/v1" + endpoint
        response = await clients["student"].post("/api/v1" + path, json={"arg": arg})
        frames = [
            json.loads(line[5:])
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        result = next((f["result"] for f in frames if "result" in f), None)
        error = next((f["error"] for f in frames if "error" in f), None)
        passed = (
            result is not None and not error
            if valid
            else bool(error) and result is None
        )
        report["results"].setdefault(key, {"cases": []})["cases"].append(
            {
                "label": "real model result"
                if valid
                else "invalid code rejected before external verification",
                "http": response.status_code,
                "passed": passed,
                "positive": valid,
                "error": error,
            }
        )
        print(key, "SSE", passed, flush=True)
        assert passed, key
        return result

    async def scenario(name, fn):
        if only and not name.startswith(only):
            return
        try:
            await fn()
            report["scenarios"][name] = {"passed": True}
        except Exception as exc:
            report["scenarios"][name] = {"passed": False, "error": str(exc)}
            print("SCENARIO FAILED", name, str(exc), flush=True)

    try:
        for role, uid in accounts.items():
            await c.identity_service.register(uid, password, uid)
            if role == "admin":
                user = await c.users.get_by_id(uid)
                user.role = UserRole.ADMIN
                await c.users.create(user)
            client = httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=180)
            token = (
                await client.post(
                    "/api/v1/app/auth/login",
                    json={"account": uid, "password": password},
                )
            ).json()["data"]["token"]
            client.headers["Authorization"] = "Bearer " + token
            clients[role] = client
        await c.extra["module_platform"].repository.db.execute(
            "UPDATE biz_module_release SET status='failed',stage='acceptance_cleanup' WHERE kind='check' AND actor LIKE 'qa_admin_%' AND status IN ('requested','queued')"
        )
        await c.extra["module_platform"].repository.db.execute(
            "UPDATE biz_developer_project SET trusted=false,auto_deploy=false WHERE id LIKE 'qa_project_%'"
        )
        uid = accounts["student"]
        await c.asset_service.save_action_plan(
            uid,
            ActionPlan(
                id="qa_plan_" + suffix,
                phases=[
                    ActionPhase(
                        name="本周",
                        date_range="验收合成数据",
                        tasks=[
                            ActionTask(id="qa_first", text="整理项目经历"),
                            ActionTask(id="qa_second", text="整理项目经历"),
                        ],
                    )
                ],
            ),
        )
        await c.asset_service.save_direction_plans(
            uid,
            [
                DirectionPlan(
                    id="qa_" + r + "_" + suffix,
                    role=r,
                    name="验收方向 " + r,
                    target_desc="接口测试",
                    fit_reason="合成测试依据",
                    main_risk="仅限验收",
                )
                for r in ["main", "parallel"]
            ],
        )
        await c.profile_service.update_field(
            uid,
            "interest",
            "软件开发",
            confidence=0.8,
            source="conversation",
            label="兴趣方向",
            evidence=["隔离验收资料"],
        )
        await c.profile_service.replace_gaps(
            uid,
            [
                ProfileGap(
                    key="experience",
                    label="实践经历",
                    reason="缺少具体项目实例",
                    suggested_next_action="描述一个项目",
                )
            ],
        )
        notice = await c.notifier.push(
            uid, title="隔离验收提醒", body="验证已读状态持久化"
        )
        # For browser checks only. Outside the repository, never part of results.
        Path("/tmp/acceptance-accounts.json").write_text(
            json.dumps({"accounts": accounts, "password": password})
        )

        async def student_writes():
            for done in [True, False]:
                await request(
                    "student",
                    "PATCH",
                    "/app/plan/action/tasks",
                    json={"task_id": "qa_first", "done": done},
                    label=f"complete={done}",
                )
                plan = await request("student", "GET", "/app/plan/action")
                tasks = {
                    t["task_id"]: t["done"] for p in plan["phases"] for t in p["tasks"]
                }
                assert tasks["qa_first"] == done and not tasks["qa_second"]
            for choice in ["main", "parallel"]:
                await request(
                    "student",
                    "POST",
                    "/app/plan/directions/qa_" + choice + "_" + suffix + "/select",
                    endpoint="/app/plan/directions/{option_id}/select",
                    label="choose " + choice,
                )
                plans = await request("student", "GET", "/app/plan/directions")
                selected = [p["id"] for p in plans["plans"] if p["selected"]]
                assert selected == ["qa_" + choice + "_" + suffix], selected
            path = "/app/notifications/" + notice.message_id + "/read"
            denied = await request(
                "other",
                "POST",
                path,
                endpoint="/app/notifications/{message_id}/read",
                label="other account changes no rows",
            )
            assert denied["read"] is False
            assert any(
                n["id"] == notice.message_id
                for n in await request("student", "GET", "/app/notifications/pending")
            )
            await request(
                "student", "POST", path, endpoint="/app/notifications/{message_id}/read"
            )
            assert not any(
                n["id"] == notice.message_id
                for n in await request("student", "GET", "/app/notifications/pending")
            )

        if only == "student":
            for k in [
                "PATCH /api/v1/app/plan/action/tasks",
                "POST /api/v1/app/plan/directions/{option_id}/select",
                "POST /api/v1/app/notifications/{message_id}/read",
            ]:
                report["results"].pop(k, None)
        await scenario("student write/readback and account isolation", student_writes)

        async def student_reads():
            await request(
                "student",
                "GET",
                "/app/theory-cards/parsons_self",
                endpoint="/app/theory-cards/{theory_id}",
            )
            await request("student", "POST", "/app/intel/refresh")
            await stream("/app/dimensions/interest", "/app/dimensions/{dimension_id}")
            await stream("/app/gaps/experience/clarify", "/app/gaps/{gap_key}/clarify")
            await stream("/app/chsi/bind", "/app/chsi/bind", arg="invalid", valid=False)
            report["limitations"].append(
                "CHSI positive verification requires a real online verification code; never simulated as success"
            )

        await scenario("remaining read and AI interfaces", student_reads)

        async def admin_modules():
            for path in [
                "/developer/context",
                "/developer/capabilities",
                "/developer/modules",
                "/developer/checks",
                "/developer/releases",
                "/developer/platform-status",
                "/developer/projects",
                "/developer/workflows",
            ]:
                await request(
                    "student", "GET", path, label="student forbidden", reject=True
                )
                await request("admin", "GET", path)
            await request(
                "student",
                "POST",
                "/app/config/reload",
                label="student forbidden",
                reject=True,
            )
            await request("admin", "POST", "/app/config/reload")
            listing = await request("admin", "GET", "/developer/modules")
            for item in listing:
                m, p = item["manifest"], item["policy"]
                p.update(
                    enabled=True,
                    reads=m.get("reads", []),
                    actions=m.get("actions", []),
                    agents=[],
                )
                await request(
                    "admin",
                    "PUT",
                    "/developer/modules/" + m["id"] + "/policy",
                    endpoint="/developer/modules/{module_id}/policy",
                    json=p,
                )
            await request("admin", "POST", "/developer/checks")
            for mode in ["fixture", "live"]:
                await request(
                    "admin",
                    "POST",
                    "/developer/modules/action_progress/preview",
                    endpoint="/developer/modules/{module_id}/preview",
                    json={"mode": mode, "fixture": "normal", "input": {}},
                    label=mode,
                )
            await request(
                "student",
                "GET",
                "/app/modules/action_progress/data",
                endpoint="/app/modules/{module_id}/data",
            )
            await request(
                "student",
                "POST",
                "/app/modules/action_progress/invoke",
                endpoint="/app/modules/{module_id}/invoke",
                json={"input": {}},
            )
            await request(
                "student",
                "POST",
                "/app/modules/action_progress/actions",
                endpoint="/app/modules/{module_id}/actions",
                json={
                    "action": "plan.task.set_done",
                    "payload": {"task_id": "qa_second", "done": True},
                },
            )
            plan = await request("student", "GET", "/app/plan/action")
            assert next(
                t
                for p in plan["phases"]
                for t in p["tasks"]
                if t["task_id"] == "qa_second"
            )["done"]

        await scenario("module permissions preview and live actions", admin_modules)

        async def workflows():
            mid = next(
                m
                for m in await request("admin", "GET", "/developer/modules")
                if m["manifest"]["id"] == "action_progress"
            )["manifest"]
            wid = "qa_flow_" + suffix
            draft = {
                "id": wid,
                "name": "隔离验收流程",
                "nodes": [
                    {
                        "id": "progress",
                        "module_id": mid["id"],
                        "module_version": mid["version"],
                        "input": {},
                    }
                ],
            }
            value = await request("admin", "POST", "/developer/workflows", json=draft)
            revision = value["revision"]
            run = await request(
                "admin",
                "POST",
                f"/developer/workflows/{wid}/run",
                endpoint="/developer/workflows/{workflow_id}/run",
                json={"mode": "fixture", "request_id": "preview_" + suffix},
            )
            assert run["status"] == "succeeded", run.get("error")
            await request(
                "admin",
                "POST",
                f"/developer/workflows/{wid}/publish",
                endpoint="/developer/workflows/{workflow_id}/publish",
                json={"expected_revision": revision},
            )
            body = {"mode": "live", "request_id": "student_" + suffix}
            run = await request(
                "student",
                "POST",
                f"/app/workflows/{wid}/run",
                endpoint="/app/workflows/{workflow_id}/run",
                json=body,
            )
            assert run["status"] == "succeeded", run.get("error")
            again = await request(
                "student",
                "POST",
                f"/app/workflows/{wid}/run",
                endpoint="/app/workflows/{workflow_id}/run",
                json=body,
                label="idempotent replay",
            )
            assert run["id"] == again["id"]
            assert await request(
                "admin",
                "GET",
                f"/developer/workflows/{wid}/runs",
                endpoint="/developer/workflows/{workflow_id}/runs",
            )
            await request(
                "admin",
                "POST",
                f"/developer/workflows/{wid}/unpublish",
                endpoint="/developer/workflows/{workflow_id}/unpublish",
                json={"expected_revision": revision},
            )
            await request(
                "student",
                "POST",
                f"/app/workflows/{wid}/run",
                endpoint="/app/workflows/{workflow_id}/run",
                json={**body, "request_id": "revoked_" + suffix},
                reject=True,
                label="unpublished rejected",
            )

        await scenario("workflow publish run replay history unpublish", workflows)

        async def projects():
            pid = "qa_project_" + suffix
            value = await request(
                "admin",
                "POST",
                "/developer/projects",
                json={"id": pid, "name": "隔离验收模块"},
            )
            await request(
                "admin",
                "PUT",
                f"/developer/projects/{pid}",
                endpoint="/developer/projects/{project_id}",
                json={
                    "revision": value["revision"],
                    "name": "验收更新名称",
                    "trusted": False,
                    "auto_deploy": False,
                    "members": [],
                },
            )
            package = await request(
                "admin",
                "GET",
                "/developer/templates",
                params={
                    "module_id": pid,
                    "name": "验收模板",
                    "owner": accounts["admin"],
                    "kind": "hybrid",
                },
                binary=True,
            )
            assert package[:2] == b"PK"
            version = await request(
                "admin",
                "POST",
                f"/developer/projects/{pid}/versions",
                endpoint="/developer/projects/{project_id}/versions",
                json={
                    "package_base64": base64.b64encode(package).decode(),
                    "base_commit": "a" * 40,
                    "request_id": "upload_" + suffix,
                },
            )
            vid = version["id"]
            versions = await request(
                "admin",
                "GET",
                f"/developer/projects/{pid}/versions",
                endpoint="/developer/projects/{project_id}/versions",
            )
            assert versions[0]["id"] == vid
            await request(
                "admin",
                "GET",
                f"/developer/versions/{vid}",
                endpoint="/developer/versions/{version_id}",
            )
            downloaded = await request(
                "admin",
                "GET",
                f"/developer/versions/{vid}/package",
                endpoint="/developer/versions/{version_id}/package",
                binary=True,
            )
            assert downloaded == package
            # Only this disposable project receives a synthetic worker failure;
            # never manufacture a successful candidate/build receipt.
            current = next(
                p
                for p in await request("admin", "GET", "/developer/projects")
                if p["id"] == pid
            )
            await request(
                "admin",
                "PUT",
                f"/developer/projects/{pid}",
                endpoint="/developer/projects/{project_id}",
                json={
                    "revision": current["revision"],
                    "name": current["name"],
                    "trusted": True,
                    "auto_deploy": False,
                    "members": [],
                },
            )
            repository = c.extra["developer_platform"].repository
            claim = await repository.claim()
            assert claim["id"] == vid
            await repository.update_version(
                vid,
                claim["lease"],
                {
                    "status": "failed",
                    "stage": "synthetic_test_failure",
                    "report": {
                        "acceptance_setup": "injected worker failure, not deployment evidence"
                    },
                },
            )
            retried = await request(
                "admin",
                "POST",
                f"/developer/versions/{vid}/retry",
                endpoint="/developer/versions/{version_id}/retry",
                label="failed version returns to queue",
            )
            assert retried["status"] == "queued"
            await request(
                "admin",
                "POST",
                f"/developer/versions/{vid}/release",
                endpoint="/developer/versions/{version_id}/release",
                reject=True,
                label="offline executor / unsigned version rejected",
            )
            report["limitations"].append(
                "Version deployment positive path requires a real source worker, candidate build/dataflow/browser evidence and executor; no fabricated gate results"
            )
            job = await request(
                "admin",
                "POST",
                "/developer/releases",
                json={
                    "commit": "a" * 40,
                    "request_id": "check_" + suffix,
                    "kind": "check",
                },
            )
            await request(
                "admin",
                "POST",
                f"/developer/releases/{job['id']}/approve",
                endpoint="/developer/releases/{job_id}/approve",
            )
            assert any(
                j["id"] == job["id"] and j["status"] == "queued"
                for j in await request("admin", "GET", "/developer/releases")
            )
            report["limitations"].append(
                "Release request/approval tested to queue only; isolated environment has no executor and never deploys"
            )

        await scenario(
            "project templates versions download and release guards", projects
        )
    finally:
        for client in clients.values():
            await client.aclose()
        for obj in reversed(c.extra.get("closables", [])):
            close = getattr(obj, "aclose", None)
            if close:
                await close()
        for entry in report["results"].values():
            entry["passed"] = all(case["passed"] for case in entry["cases"])
            entry["positive_verified"] = any(
                case["positive"] and case["passed"] for case in entry["cases"]
            )
        report["limitations"] = list(dict.fromkeys(report["limitations"]))
        Path("/results/remaining-acceptance-results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    assert all(s["passed"] for s in report["scenarios"].values()), (
        "Acceptance failed; see report"
    )


if __name__ == "__main__":
    asyncio.run(main())
