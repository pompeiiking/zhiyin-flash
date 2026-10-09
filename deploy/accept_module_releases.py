"""Fault-injection acceptance against a private .platform Git snapshot only.

Requires one successful base release. Makes build/startup-failure commits in the
snapshot, verifies recovery, adds a module using only the documented generator,
deploys it, verifies grants/preview, then restores the original successful version.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from module_executor import Executor, process_lock, request

ROOT = Path(__file__).resolve().parents[1]


def main(faults=True):
    config = json.loads((ROOT / ".platform/validation-executor.json").read_text())
    executor = Executor(config)
    assert executor.repo.is_relative_to(ROOT / ".platform"), "Only a private acceptance snapshot may be mutated"
    base = executor.actual_revision()
    assert len(base) == 40, "A successful staging release is required first"
    from module_executor import read_env
    control = read_env(Path(config["workbench_env_file"]))
    auth = request(executor.base, "/api/v1/app/auth/login", body={"account": "admin", "password": control["PLATFORM_ACCOUNT_PASSWORD"]})
    results = [] if faults else json.loads((ROOT / ".platform/acceptance/releases.json").read_text(encoding="utf-8"))
    evidence = ROOT / ".platform/acceptance/releases.json"
    def git(*args):
        return subprocess.check_output(["git", "-C", str(executor.repo), *args]).decode().strip()
    def commit(message):
        git("add", ".")
        git("-c", "user.name=Module Acceptance", "-c", "user.email=module-acceptance@localhost", "commit", "-qm", message)
        return git("rev-parse", "HEAD")
    def run(sha, kind="deploy", expected="succeeded"):
        job = request(executor.base, "/api/v1/developer/releases", token=auth["token"],
                      body={"commit": sha, "kind": kind, "request_id": "regression_" + uuid4().hex})
        request(executor.base, f"/api/v1/developer/releases/{job['id']}/approve", token=auth["token"], body={})
        claimed = request(executor.base, "/api/v1/developer/executor/claim", token=executor.token, body={})
        assert claimed["id"] == job["id"]
        executor.execute(claimed)
        latest = next(j for j in request(executor.base, "/api/v1/developer/releases", token=auth["token"]) if j["id"] == job["id"])
        assert latest["status"] == expected, latest
        results.append({"commit": sha, "job": job["id"], "kind": kind, "status": latest["status"], "installed": executor.actual_revision()})
        evidence.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return latest
    with process_lock(executor.root / "executor.lock"):
        dockerfile = executor.repo / "Dockerfile"
        original = subprocess.check_output(["git", "-C", str(executor.repo), "show", base + ":Dockerfile"])
        if faults:
            dockerfile.write_bytes(original + b'\nRUN python -c "raise SystemExit(42)"\n')
            failed_build = commit("Acceptance only: intentional image build failure")
            run(failed_build, expected="failed")
            assert executor.actual_revision() == base
            import re
            dockerfile.write_text(re.sub(r'^CMD .*$', 'CMD ["python", "-c", "raise SystemExit(42)"]', original.decode(), flags=re.M), encoding="utf-8")
            failed_start = commit("Acceptance only: intentional startup failure")
            run(failed_start, expected="rolled_back")
            assert executor.actual_revision() == base
        dockerfile.write_bytes(original)
        template = executor.repo / "zhiyin-src/template"
        subprocess.run([sys.executable, str(template / "scripts/module_cli.py"), "new", "acceptance_card",
                        "--name", "独立接入验收卡", "--owner", "自动试接入"], check=True, cwd=template)
        module_commit = commit("Acceptance only: add one generated module directory")
        changed = git("diff", "--name-only", base, module_commit).splitlines()
        assert changed and all(p.startswith("zhiyin-src/template/zhiyin-modules/zhiyin_modules/acceptance_card/") for p in changed), changed
        run(module_commit)
        staging = request(executor.target, "/api/v1/app/auth/login", body={"account": executor.env["PLATFORM_SMOKE_ACCOUNT"], "password": executor.env["PLATFORM_ACCOUNT_PASSWORD"]})
        def api(path, body=None, method=None):
            return request(executor.target, "/api/v1" + path, token=staging["token"], body=body, method=method)
        module = next(m for m in api("/developer/modules") if m["manifest"]["id"] == "acceptance_card")
        assert not module["policy"]["enabled"]
        api("/developer/modules/acceptance_card/policy", {**module["policy"], "enabled": True, "reads": ["plan.read"], "actions": ["plan.task.set_done"]}, "PUT")
        live = api("/app/modules/acceptance_card/data")
        assert live == api("/app/modules/action_progress/data")
        assert not api("/developer/modules/acceptance_card/preview", {"mode": "fixture"})["empty"]
        results.append({"check": "generated_module_directory_only", "commit": module_commit, "files": changed, "preview_and_live_passed": True})
        evidence.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        # A data change must survive application-image rollback.
        api("/app/modules/acceptance_card/actions", {"action": "plan.task.set_done", "payload": {"task_id": "sample-intro", "done": True}})
        run(base, kind="rollback")
        assert api("/app/modules/action_progress/data")["data"]["completed"] == 2
        assert all(m["manifest"]["id"] != "acceptance_card" for m in api("/app/modules"))
        api("/app/modules/action_progress/actions", {"action": "plan.task.set_done", "payload": {"task_id": "sample-intro", "done": False}})
        results.append({"check": "rollback_preserves_business_data_and_hides_uninstalled_module", "passed": True})
        evidence.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS build failure, startup recovery, new module deployment, full-image rollback and durable data", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-faults", action="store_true", help="Continue with template-only acceptance after recorded fault tests")
    main(not parser.parse_args().skip_faults)
