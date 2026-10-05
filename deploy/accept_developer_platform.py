"""Exercise the developer v2 lifecycle on the isolated local workbench/staging.

Phases are explicit so the host workers can run between submission and verification.
Only synthetic module projects/accounts are used. Credentials never enter evidence.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from module_executor import read_env, request

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / ".platform/acceptance"
STATE = DIRECTORY / "developer-v2-lifecycle.json"
WORKBENCH = "http://127.0.0.1:8014"
STAGING = "http://127.0.0.1:5175"


class Acceptance:
    def __init__(self):
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        self.state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"checks": []}
        self.tokens = {}
        for account in ("admin", "module_developer", "module_student"):
            password = read_env(ROOT / ".platform/workbench.env")["PLATFORM_ACCOUNT_PASSWORD"]
            value = request(WORKBENCH, "/api/v1/app/auth/login", body={"account": account, "password": password})
            self.tokens[account] = value["token"]

    def save(self):
        STATE.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(self, name, **values):
        self.state["checks"].append({"check": name, "passed": True, **values})
        self.save()
        print("PASS " + name, flush=True)

    def api(self, path, body=None, actor="module_developer", method=None):
        return request(WORKBENCH, "/api/v1" + path, token=self.tokens[actor], body=body, method=method)

    def denied(self, path, body=None, actor="module_developer", method=None, status=None):
        try:
            self.api(path, body, actor, method)
        except urllib.error.HTTPError as exc:
            if status is not None:
                assert exc.code == status, (exc.code, exc.read().decode())
            assert 400 <= exc.code < 500
            return
        raise AssertionError("Request unexpectedly succeeded: " + path)

    def configure(self, **changes):
        project = next(p for p in self.api("/developer/projects", actor="admin") if p["id"] == self.state["project_id"])
        body = {key: project[key] for key in ("revision", "name", "description", "members", "trusted", "auto_deploy")}
        body.update(changes)
        return self.api("/developer/projects/" + project["id"], body, "admin", "PUT")

    def package(self, version, *, wrong_live_assertion=False):
        query = urllib.parse.urlencode({"kind": "hybrid", "module_id": self.state["project_id"],
            "name": "自动发布验收示例", "owner": "module_developer"})
        req = urllib.request.Request(WORKBENCH + "/api/v1/developer/templates?" + query,
            headers={"Authorization": "Bearer " + self.tokens["module_developer"]})
        with urllib.request.urlopen(req, timeout=30) as response:
            source = response.read()
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in original.namelist():
                data = original.read(name)
                if name == "manifest.json":
                    manifest = json.loads(data)
                    manifest["version"] = version
                    data = json.dumps(manifest, ensure_ascii=False).encode()
                if name == "dataflow.json" and wrong_live_assertion:
                    contract = json.loads(data)
                    contract["live_assertions"][0]["equals"] = 999
                    data = json.dumps(contract).encode()
                archive.writestr(name, data)
        data = output.getvalue()
        (DIRECTORY / (self.state["project_id"] + "-" + version + ".zip")).write_bytes(data)
        return base64.b64encode(data).decode()

    def upload_body(self, version, base_version=None, **options):
        platform = self.api("/developer/platform-status")
        assert platform["worker"]["healthy"], "Start the source worker before submitting acceptance"
        return {"package_base64": self.package(version, **options), "channel": "main",
            "base_version_id": base_version, "base_commit": platform["base_commit"], "request_id": uuid.uuid4().hex}

    def prepare(self):
        assert "bad_version_id" not in self.state, "This evidence already has a version; use its next phase"
        self.denied("/developer/projects", actor="module_student", status=401)
        self.state["original_health"] = request("http://127.0.0.1:8000", "/healthz")
        self.state.setdefault("project_id", "release_demo_" + uuid.uuid4().hex[:8])
        path = "/developer/projects/" + self.state["project_id"]
        project = next((p for p in self.api("/developer/projects") if p["id"] == self.state["project_id"]), None)
        if project is None:
            project = self.api("/developer/projects", {"id": self.state["project_id"], "name": "自动发布验收示例",
                "description": "自动化验收创建：演示错误阻断、修复上传、真实数据流和蓝绿发布。"})
        self.save()
        body = {key: project[key] for key in ("revision", "name", "description", "members", "trusted", "auto_deploy")}
        self.denied(path, {**body, "trusted": True}, method="PUT", status=401)
        configured = self.configure(members=["admin"])
        self.denied(path, body, method="PUT", status=409)
        self.denied(path, {**body, "revision": configured["revision"], "members": ["module_student"]}, method="PUT", status=422)
        upload = self.upload_body("0.1.0", wrong_live_assertion=True)
        version = self.api(path + "/versions", upload)
        assert version["stage"] == "awaiting_trust"
        assert self.api(path + "/versions", upload)["id"] == version["id"]
        self.denied(path + "/versions", {**upload, "request_id": uuid.uuid4().hex}, status=409)
        self.denied(path + "/versions", {**upload, "package_base64": self.package("0.1.1")}, status=409)
        self.state["bad_version_id"] = version["id"]
        self.state["before_revision"] = request(STAGING, "/healthz")["revision"]
        self.record("real_database_roles_project_cas_immutable_version_and_idempotency", version_id=version["id"])
        self.configure(trusted=True, auto_deploy=True)
        self.record("trusted_project_enters_automatic_acceptance")

    def submit_good(self):
        previous = self.api("/developer/versions/" + self.state["bad_version_id"])
        assert previous["status"] == "failed", previous["status"]
        assert any(g["name"] == "dataflow" and g["status"] == "failed" for g in previous["report"]["gates"]), previous["report"]
        assert not previous["release_job_id"]
        assert request(STAGING, "/healthz")["revision"] == self.state["before_revision"]
        self.record("incorrect_live_result_blocks_release_and_preserves_running_version", report=previous["report"])
        body = self.upload_body("0.1.1", previous["id"])
        good = self.api("/developer/projects/" + self.state["project_id"] + "/versions", body)
        self.state["good_version_id"] = good["id"]
        self.record("corrected_version_uploaded", version_id=good["id"])

    def monitor(self):
        if self.state.get("availability"):
            self.state.setdefault("availability_attempts", []).append(self.state["availability"])
        stop = threading.Event()
        samples = []
        def probe():
            while not stop.is_set():
                try:
                    value = request(STAGING, "/healthz", timeout=3)
                    assert value["status"] == "ok"
                    samples.append({"ok": True, "revision": value["revision"]})
                except Exception as exc:  # noqa: BLE001 - Every observable outage belongs in the acceptance evidence.
                    samples.append({"ok": False, "error": str(exc)})
                stop.wait(.4)
        thread = threading.Thread(target=probe, daemon=True)
        thread.start()
        deadline = time.monotonic() + 2400
        last = ""
        try:
            while time.monotonic() < deadline:
                try:
                    version = self.api("/developer/versions/" + self.state["good_version_id"])
                except (urllib.error.URLError, TimeoutError, http.client.HTTPException) as exc:
                    if isinstance(exc, urllib.error.HTTPError) and exc.code < 500:
                        raise
                    print("Control plane reconnecting: " + type(exc).__name__, flush=True)
                    time.sleep(2)
                    continue
                state = version["status"] + "/" + version["stage"]
                assert version["status"] != "failed", version["report"]
                if version["release_job_id"]:
                    job = next(j for j in self.api("/developer/releases") if j["id"] == version["release_job_id"])
                    state += " → " + job["status"] + "/" + job["stage"]
                    assert job["status"] not in ("failed", "rolled_back"), job
                    if job["status"] == "succeeded":
                        assert request(STAGING, "/healthz")["revision"] == version["candidate_commit"]
                        assert request(STAGING, "/version.json")["revision"] == version["candidate_commit"]
                        self.state["installed_revision"] = version["candidate_commit"]
                        self.state["release_job_id"] = job["id"]
                        self.record("uploaded_exact_commit_deployed_with_accepted_images", report=version["report"], release=job)
                        break
                if state != last:
                    print(state, flush=True)
                    last = state
                time.sleep(2)
            else:
                raise TimeoutError("Automatic acceptance/release did not finish")
        finally:
            stop.set()
            thread.join(timeout=5)
            self.state["availability"] = {"samples": len(samples), "failures": [v for v in samples if not v["ok"]],
                "observed_revisions": sorted({v["revision"] for v in samples if v["ok"]})}
            self.save()
        assert samples and all(v["ok"] for v in samples), self.state["availability"]
        check = "bluegreen_public_health_continuity" if len(self.state["availability"]["observed_revisions"]) > 1 else "post_release_public_health_sample"
        self.record(check, **self.state["availability"])

    def verify(self):
        password = read_env(ROOT / ".platform/staging.env")["PLATFORM_ACCOUNT_PASSWORD"]
        token = request(STAGING, "/api/v1/app/auth/login", body={"account": "admin", "password": password})["token"]
        def api(path, body=None, method=None):
            return request(STAGING, "/api/v1" + path, token=token, body=body, method=method)
        module = next(m for m in api("/developer/modules") if m["manifest"]["id"] == self.state["project_id"])
        expected_version = self.state.get("expected_version", "0.1.1")
        assert module["manifest"]["version"] == expected_version
        previously_authorized = any(check["check"] == "uploaded_module_authorized_and_reads_real_core_data" for check in self.state["checks"])
        assert module["policy"]["enabled"] == previously_authorized
        if previously_authorized:
            assert module["policy"]["reads"] == module["manifest"]["reads"]
            assert module["policy"]["actions"] == module["manifest"]["actions"]
            self.record("module_authorization_preserved_across_update", version=expected_version)
        policy = {**module["policy"], "enabled": True, "reads": module["manifest"]["reads"], "actions": module["manifest"]["actions"], "agents": ["path_planner"]}
        api("/developer/modules/" + self.state["project_id"] + "/policy", policy, "PUT")
        result = api("/app/modules/" + self.state["project_id"] + "/invoke", {"input": {}, "expected_version": expected_version})
        plan = api("/app/plan/action")
        tasks = [task for phase in plan["phases"] for task in phase["tasks"]]
        assert result["data"]["total"] == len(tasks)
        assert result["data"]["completed"] == sum(task["done"] for task in tasks)
        assert result["trace"]
        self.record("uploaded_module_authorized_and_reads_real_core_data", result=result)
        original = self.state["original_health"]
        current = request("http://127.0.0.1:8000", "/healthz")
        assert current.get("revision") == original.get("revision") and current["status"] == "ok"
        self.record("original_5173_service_revision_preserved")

    def workflows(self):
        modules = {m["manifest"]["id"]: m for m in self.api("/developer/modules")}
        original = {mid: modules[mid]["policy"] for mid in ("action_progress", "plan_progress_skill")}
        def configure(mid, value):
            current = next(m for m in self.api("/developer/modules") if m["manifest"]["id"] == mid)["policy"]
            return self.api("/developer/modules/" + mid + "/policy", {**value, "revision": current["revision"]}, "admin", "PUT")
        before = self.api("/app/plan/action")
        other_before = self.api("/app/plan/action", actor="module_student")
        task = before["phases"][-1]["tasks"][-1]
        workflow_id = "accept_flow_" + uuid.uuid4().hex[:12]
        try:
            for mid, policy in original.items():
                configure(mid, {**policy, "enabled": True, "reads": ["plan.read"], "actions": modules[mid]["manifest"]["actions"]})
            definition = {"id": workflow_id, "name": "数据回传与操作验收", "expected_revision": 0,
                "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"], "additionalProperties": False},
                "nodes": [
                    {"id": "plan", "module_id": "action_progress"},
                    {"id": "skill", "module_id": "plan_progress_skill", "bindings": {"expected_total": "plan/data/total", "expected_completed": "plan/data/completed"}},
                    {"id": "complete", "module_id": "action_progress", "operation": "action", "action": "plan.task.set_done",
                        "input": {"done": not task["done"]}, "bindings": {"task_id": "$input/task_id"}}]}
            draft = self.api("/developer/workflows", definition)
            published = self.api("/developer/workflows/" + workflow_id + "/publish", {"expected_revision": draft["revision"]})
            assert published["published_revision"] == 1
            body = {"input": {"task_id": task["task_id"]}, "mode": "live", "confirm_actions": True,
                "request_id": uuid.uuid4().hex, "expected_revision": 1}
            run = self.api("/app/workflows/" + workflow_id + "/run", body)
            assert run["status"] == "succeeded" and run["action_committed"], run
            assert run["outputs"]["plan"]["data"]["total"] == run["outputs"]["skill"]["data"]["total"]
            assert self.api("/app/workflows/" + workflow_id + "/run", body) == run
            after = self.api("/app/plan/action")
            assert next(t for p in after["phases"] for t in p["tasks"] if t["task_id"] == task["task_id"])["done"] == (not task["done"])
            assert self.api("/app/plan/action", actor="module_student") == other_before
            second = self.api("/developer/workflows", {**definition, "expected_revision": 1, "name": "待发布的新草稿"})
            assert second["revision"] == 2 and second["published_revision"] == 1
            self.denied("/developer/workflows", {**definition, "expected_revision": 1}, status=409)
            assert self.api("/app/workflows/" + workflow_id + "/run", body) == run
            configure("plan_progress_skill", {**original["plan_progress_skill"], "enabled": False})
            self.denied("/app/workflows/" + workflow_id + "/run", body, status=401)
            self.record("published_workflow_real_upstream_binding_write_readback_idempotency_and_revocation", workflow_id=workflow_id, run=run)
        finally:
            self.api("/app/modules/action_progress/actions", {"action": "plan.task.set_done", "payload": {"task_id": task["task_id"], "done": task["done"]}})
            for mid in reversed(original):
                configure(mid, original[mid])
        self.record("workflow_acceptance_restored_synthetic_task_and_grants")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "submit-good", "monitor", "verify", "workflows"))
    args = parser.parse_args()
    getattr(Acceptance(), args.phase.replace("-", "_"))()
