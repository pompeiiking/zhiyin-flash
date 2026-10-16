"""Real HTTP/PostgreSQL acceptance of worker protocols in a disposable workbench.

Never deploys or manufactures successful build/browser evidence. Database writes
outside HTTP only create an admin account and advance this run's lease clock.
Run inside the isolated API container, with /results mounted to the evidence folder.
"""
import asyncio
import base64
import datetime
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

import httpx
from zhiyin_boot.container import build_container
from zhiyin_boot.settings import Settings
from zhiyin_kernel.enums import UserRole


async def main():
    settings = Settings.from_env()
    if (os.environ.get("ZHIYIN_DATAFLOW_ISOLATED") != "1"
            or os.environ.get("ZHIYIN_MODULE_ENV") != "workbench"
            or "@db:5432/acceptance" not in settings.postgres_dsn):
        raise RuntimeError("Refusing to run outside the disposable acceptance DB")
    secret = os.environ["ZHIYIN_EXECUTOR_TOKEN"]
    assert len(secret) >= 32
    container = build_container(settings)
    db = container.extra["developer_platform"].repository.db
    suffix = uuid4().hex[:10]
    uid, pid = "qa_worker_" + suffix, "qa_worker_" + suffix
    report = {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "environment": "isolated PostgreSQL + real HTTP; protocol fault injection only",
        "results": {}, "passed": False,
        "limitations": [
            "No source worker build or deployment executor process is started.",
            "No successful build/dataflow/browser/deployment receipts are fabricated.",
            "Automatic release is verified for denial only; real release remains pending.",
            "Lease expiry is advanced in PostgreSQL for this run's own records only.",
        ],
    }
    clients = {name: httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30)
               for name in ("worker", "admin", "anonymous", "invalid")}
    clients["worker"].headers["Authorization"] = "Bearer " + secret
    clients["invalid"].headers["Authorization"] = "Bearer " + uuid4().hex
    vid = None
    jobs = []

    async def req(method, path, *, actor="worker", endpoint=None, label,
                  reject=False, binary=False, check=None, **kwargs):
        key = method + " /api/v1" + (endpoint or path)
        case = {"label": label, "positive": not reject, "passed": False}
        report["results"].setdefault(key, {"cases": []})["cases"].append(case)
        response = await clients[actor].request(method, "/api/v1" + path, **kwargs)
        case["http"] = response.status_code
        payload = {} if binary and response.is_success else response.json()
        case["code"] = payload.get("code")
        ok = response.is_success and (binary or payload.get("code") == 0)
        value = response.content if binary and ok else payload.get("data")
        passed = (not ok and response.status_code < 500) if reject else ok
        if passed and check:
            passed = bool(check(value))
        case["passed"] = passed
        if reject or not passed:
            case["message"] = payload.get("message", "unexpected response")
        print(label, passed, flush=True)
        assert passed, f"{key}: {label}: HTTP {response.status_code}"
        return value

    async def configure(*, trusted=True, auto=False):
        projects = await req("GET", "/developer/projects", actor="admin", label="read project revision")
        project = next(p for p in projects if p["id"] == pid)
        return await req("PUT", f"/developer/projects/{pid}", actor="admin",
                         endpoint="/developer/projects/{project_id}", label="configure project authorization",
                         json={"revision": project["revision"], "name": "Worker protocol acceptance",
                               "trusted": trusted, "auto_deploy": auto, "members": []})

    async def update(body, *, label, reject=False, check=None):
        return await req("POST", f"/developer/source-worker/versions/{vid}",
                         endpoint="/developer/source-worker/versions/{version_id}",
                         json=body, label=label, reject=reject, check=check)

    async def release(*, label):
        return await req("POST", f"/developer/source-worker/versions/{vid}/release",
                         endpoint="/developer/source-worker/versions/{version_id}/release",
                         label=label, reject=True)

    try:
        password = uuid4().hex
        await container.identity_service.register(uid, password, uid)
        user = await container.users.get_by_id(uid)
        user.role = UserRole.ADMIN
        await container.users.create(user)
        response = await clients["admin"].post("/api/v1/app/auth/login", json={"account": uid, "password": password})
        clients["admin"].headers["Authorization"] = "Bearer " + response.json()["data"]["token"]
        dummy = "0" * 32
        endpoints = [
            ("POST", "/developer/executor/claim", None),
            ("GET", "/developer/executor/configuration", None),
            ("POST", "/developer/executor/{job_id}", {"lease": dummy}),
            ("GET", "/developer/executor/{job_id}/authorization", None),
            ("POST", "/developer/source-worker/claim", None),
            ("POST", "/developer/source-worker/heartbeat", {"worker_id": pid, "base_commit": "a" * 40}),
            ("GET", "/developer/source-worker/ready", None),
            ("GET", "/developer/source-worker/versions/{version_id}", None),
            ("POST", "/developer/source-worker/versions/{version_id}", {"lease": dummy}),
            ("GET", "/developer/source-worker/versions/{version_id}/package", None),
            ("POST", "/developer/source-worker/versions/{version_id}/release", None),
            ("POST", "/developer/source-worker/versions/{version_id}/retry", None),
        ]
        for method, endpoint, body in endpoints:
            for actor in ("anonymous", "invalid", "admin"):
                await req(method, endpoint.format(job_id=dummy, version_id=dummy),
                          actor=actor, endpoint=endpoint, json=body, reject=True,
                          label=actor + " cannot use machine credentials")
        await req("GET", "/developer/executor/configuration", label="read real module policies",
                  check=lambda x: isinstance(x, dict) and bool(x))
        await req("POST", "/developer/source-worker/heartbeat", label="persist worker heartbeat",
                  json={"worker_id": pid, "base_commit": "a" * 40, "rules_version": "3"},
                  check=lambda x: x["ok"] is True)
        await req("GET", "/developer/platform-status", actor="admin", label="heartbeat visible to management",
                  check=lambda x: x["worker"]["healthy"] and x["worker"]["rules_version"] == "3")
        await req("POST", "/developer/projects", actor="admin", label="create isolated project",
                  json={"id": pid, "name": "Worker protocol acceptance"})
        package = await req("GET", "/developer/templates", actor="admin", binary=True,
                            label="download real module template", params={"module_id": pid, "name": "Acceptance", "owner": uid})
        version = await req("POST", f"/developer/projects/{pid}/versions", actor="admin",
                            endpoint="/developer/projects/{project_id}/versions", label="upload immutable source archive",
                            json={"package_base64": base64.b64encode(package).decode(), "base_commit": "a" * 40,
                                  "request_id": "worker_" + suffix})
        vid = version["id"]
        # The protocol hashes canonical UTF-8 sources, not ZIP timestamps/order.
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            sources = {name.removeprefix(pid + "/"): archive.read(name).decode("utf-8-sig")
                       for name in archive.namelist() if not name.endswith("/")}
        digest = hashlib.sha256(json.dumps(sources, sort_keys=True, ensure_ascii=False,
                                           separators=(",", ":")).encode()).hexdigest()
        assert digest == version["digest"]
        await req("POST", "/developer/source-worker/claim", label="untrusted source cannot be claimed", check=lambda x: x is None)
        await configure()
        claims = await asyncio.gather(*[
            req("POST", "/developer/source-worker/claim", label="concurrent source claim") for _ in range(2)])
        claimed = [x for x in claims if x]
        assert len(claimed) == 1 and claimed[0]["id"] == vid
        lease = claimed[0]["lease"]
        await req("GET", f"/developer/source-worker/versions/{vid}",
                  endpoint="/developer/source-worker/versions/{version_id}", label="read claimed version without exposing lease",
                  check=lambda x: x["status"] == "running" and "lease" not in x)
        await req("GET", f"/developer/source-worker/versions/{vid}/package", binary=True,
                  endpoint="/developer/source-worker/versions/{version_id}/package", label="source download matches immutable digest",
                  check=lambda x: x == package)
        await update({"lease": dummy, "stage": "invalid"}, label="wrong source lease rejected", reject=True)
        await update({"lease": lease, "stage": "protocol_acceptance", "event": {"message": "Protocol only"}},
                     label="valid source lease progress persisted", check=lambda x: x["stage"] == "protocol_acceptance")
        await db.execute("UPDATE biz_developer_version SET lease_until=now()-interval '1 second' WHERE id=$1", vid)
        await update({"lease": lease}, label="expired source lease rejected", reject=True)
        reclaimed = await req("POST", "/developer/source-worker/claim", label="expired source job reclaimed",
                              check=lambda x: x["id"] == vid and x["lease"] != lease)
        await update({"lease": lease}, label="replaced source lease rejected", reject=True)
        lease = reclaimed["lease"]
        await configure(trusted=False)
        await update({"lease": lease}, label="revoked source authorization rejects update", reject=True)
        await configure()
        await update({"lease": lease, "status": "failed", "stage": "protocol_test_failure",
                      "report": {"acceptance_setup": "intentional failure; no build executed"}},
                     label="source failure recorded", check=lambda x: x["status"] == "failed")
        await update({"lease": lease}, label="terminal source result immutable", reject=True)
        retried = await req("POST", f"/developer/source-worker/versions/{vid}/retry",
                            endpoint="/developer/source-worker/versions/{version_id}/retry", label="retry retains failed attempt",
                            check=lambda x: x["status"] == "queued" and bool(x["report"]["previous_attempts"]))
        assert retried["candidate_commit"] == ""
        claimed = await req("POST", "/developer/source-worker/claim", label="retry is claimable")
        lease = claimed["lease"]
        await update({"lease": lease, "status": "failed", "stage": "protocol_test_failure"}, label="finish retried protocol failure")
        await release(label="automatic release disabled rejects publication")
        await configure(auto=True)
        await release(label="failed candidate cannot pass release gates")
        await req("GET", "/developer/source-worker/ready", label="failed candidate excluded from ready queue",
                  check=lambda x: not any(v["id"] == vid for v in x))
        await req("GET", f"/developer/source-worker/versions/{dummy}",
                  endpoint="/developer/source-worker/versions/{version_id}", label="missing source version rejected", reject=True)

        job = await req("POST", "/developer/releases", actor="admin", label="request isolated check job",
                        json={"kind": "check", "commit": "a" * 40, "request_id": "worker_check_" + suffix})
        jid = job["id"]
        jobs.append(jid)
        await req("POST", f"/developer/releases/{jid}/approve", actor="admin",
                  endpoint="/developer/releases/{job_id}/approve", label="approve isolated check job")
        claims = await asyncio.gather(*[req("POST", "/developer/executor/claim", label="concurrent executor claim") for _ in range(2)])
        claimed = [x for x in claims if x]
        assert len(claimed) == 1 and claimed[0]["id"] == jid
        lease = claimed[0]["lease"]
        await req("GET", f"/developer/executor/{jid}/authorization", endpoint="/developer/executor/{job_id}/authorization",
                  label="fixed-commit authorization readable", check=lambda x: x["allowed"] is True)
        await req("GET", f"/developer/executor/{dummy}/authorization", endpoint="/developer/executor/{job_id}/authorization",
                  label="unknown executor job rejected", reject=True)

        async def executor_update(body, label, *, reject=False, check=None):
            return await req("POST", f"/developer/executor/{jid}", endpoint="/developer/executor/{job_id}",
                             json=body, label=label, reject=reject, check=check)

        await executor_update({"lease": dummy}, "wrong executor lease rejected", reject=True)
        await executor_update({"lease": lease, "stage": "protocol_acceptance", "event": {"message": "No build executed"}},
                              "executor progress persisted", check=lambda x: x["stage"] == "protocol_acceptance")
        await req("GET", "/developer/releases", actor="admin", label="management never receives live executor lease",
                  check=lambda x: all(not j["lease"] for j in x))
        await db.execute("UPDATE biz_module_release SET lease_until=now()-interval '1 second' WHERE id=$1", jid)
        await executor_update({"lease": lease}, "expired executor lease rejected", reject=True)
        reclaimed = await req("POST", "/developer/executor/claim", label="expired executor resumes with new lease",
                              check=lambda x: x["id"] == jid and x["lease"] != lease and x["result"]["resuming"])
        await executor_update({"lease": lease}, "replaced executor lease rejected", reject=True)
        lease = reclaimed["lease"]
        await executor_update({"lease": lease, "status": "failed", "stage": "protocol_test_failure",
                               "result": {"acceptance_setup": "intentional failure; no deployment"}},
                              "executor failure recorded", check=lambda x: x["status"] == "failed")
        await executor_update({"lease": lease, "status": "succeeded"}, "terminal executor result cannot be rewritten", reject=True)
        await req("POST", "/developer/executor/claim", label="completed executor job not reclaimed", check=lambda x: x is None)
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["case_count"] = sum(len(x["cases"]) for x in report["results"].values())
        Path("/results/服务间接口验收结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Prevent interrupted tests leaving claimable work; only our own IDs.
        if vid:
            await db.execute("UPDATE biz_developer_project SET trusted=false,auto_deploy=false WHERE id=$1", pid)
        for jid in jobs:
            await db.execute("UPDATE biz_module_release SET status='failed',stage='protocol_cleanup' WHERE id=$1 AND status IN ('requested','queued','running')", jid)
        for client in clients.values():
            await client.aclose()
        for resource in reversed(container.extra.get("closables", [])):
            close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
            if close:
                result = close()
                if inspect.isawaitable(result):
                    await result
    print(json.dumps({"passed": report["passed"], "cases": report["case_count"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
