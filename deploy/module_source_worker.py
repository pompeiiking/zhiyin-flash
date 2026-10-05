"""Build uploaded team modules in isolated checkouts and validate before release.

Only authenticated project packages enter this worker. No command or filesystem
path from an API request is executed. Main workspaces and production are untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from uuid import uuid4

from module_executor import Executor, process_lock, request

MODULE_ROOT = "zhiyin-src/template/zhiyin-modules/zhiyin_modules"
REQUIRED_GATES = ("contracts", "tests", "build", "dataflow")


def package_sources(raw, project_id, digest):
    """Recheck paths and checksum at the host boundary before any extraction."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", project_id) or len(raw) > 2 * 1024 * 1024:
        raise ValueError("Invalid package identity or size")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 100 or sum(item.file_size for item in entries) > 8 * 1024 * 1024:
            raise ValueError("Package limit exceeded")
        files = {}
        for item in entries:
            name = item.filename
            if item.is_dir() and name == project_id + "/":
                continue
            if name.startswith(project_id + "/"):
                name = name[len(project_id) + 1:]
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*\.(py|json|vue)", name):
                raise ValueError("Unsafe source path")
            if name.lower() in {"conftest.py", "sitecustomize.py", "usercustomize.py"} or name.casefold() in {n.casefold() for n in files}:
                raise ValueError("Duplicate or reserved source file")
            files[name] = archive.read(item).decode("utf-8-sig")
    actual = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if actual != digest:
        raise ValueError("Package digest mismatch")
    return files


class SourceWorker(Executor):
    def __init__(self, config):
        super().__init__(config)
        self.worker_id = config.get("worker_id", "source-" + uuid4().hex[:12])
        self.base_revision = config["source_base_commit"]
        self.report = {}
        self.stage = "queued"

    def api(self, path, body=None):
        return request(self.base, "/api/v1/developer/source-worker" + path, token=self.token, body=body)

    def update(self, **values):
        if "result" in values:
            values["report"] = values.pop("result")
        return self.api(f"/versions/{self.job['id']}", {"lease": self.job["lease"], **values})

    def log(self, stage, message):
        message = self.redact(str(message))
        # Low-level build output retains the owning gate rather than pretending
        # that an entire stage has already passed.
        self.update(stage=self.stage, event={"stage": stage, "message": message})
        print(f"[{self.job['id']}:{stage}] {message[-700:]}", flush=True)

    def worker_status(self):
        actual = self.actual_revision()
        base = actual if actual and self.has_commit(actual) and self.ancestor(self.base_revision, actual) else self.base_revision
        self.api("/heartbeat", {"worker_id": self.worker_id, "base_commit": base,
            "environment_revision": actual, "rules_version": "3"})
        return actual

    def has_commit(self, revision):
        return subprocess.run(["git", "-C", str(self.repo), "cat-file", "-e", revision + "^{commit}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0

    def ancestor(self, first, second):
        return subprocess.run(["git", "-C", str(self.repo), "merge-base", "--is-ancestor", first, second],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0

    def heartbeat(self):
        while not self.stopping.wait(15):
            try:
                self.update()
                self.worker_status()
            except Exception:  # noqa: BLE001 - loss fences every later host action
                self.lost.set()
                return

    def package(self, version):
        req = urllib.request.Request(self.base + f"/api/v1/developer/source-worker/versions/{version['id']}/package",
                                     headers={"Authorization": "Bearer " + self.token})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        return package_sources(data, version["project_id"], version["digest"])

    def candidate(self, version, files, actual):
        base = version["base_commit"]
        if not actual:
            raise ValueError("无法确认目标环境当前版本，恢复环境健康后再验收，禁止盲目覆盖")
        if not self.has_commit(base):
            raise ValueError("平台基础提交不存在于受控源码仓库")
        if actual and not self.has_commit(actual):
            raise ValueError("已安装版本尚未纳入受控源码仓库，禁止从旧基线覆盖，请先同步该提交")
        module_path = MODULE_ROOT + "/" + version["project_id"]
        # Carry forward another developer's already published modules. A change
        # to this same module is an explicit conflict, never a silent overwrite.
        if actual and actual != base and not self.ancestor(actual, base):
            if not self.ancestor(base, actual):
                raise ValueError("平台基线与已安装版本分叉，需要先合并平台代码并重新验收")
            diff = self.run(["git", "-C", self.repo, "diff", "--name-only", base, actual, "--", module_path]).strip()
            if diff:
                parent_id = version.get("base_version_id")
                parent = self.api(f"/versions/{parent_id}") if parent_id else None
                parent_commit = parent.get("candidate_commit") if parent else None
                matched = parent and parent["project_id"] == version["project_id"] and parent_commit and self.has_commit(parent_commit)
                if not matched or self.run(["git", "-C", self.repo, "diff", "--name-only", parent_commit, actual, "--", module_path]).strip():
                    raise ValueError("同一模块已经有新版本上线，请下载新版本并更新提交基线")
            base = actual
        directory = self.root / "sources" / (version["id"] + "-" + version["lease"])
        directory.parent.mkdir(parents=True, exist_ok=True)
        self.run(["git", "clone", "--no-hardlinks", "--no-checkout", self.repo, directory])
        self.run(["git", "-C", directory, "config", "core.autocrlf", "false"])
        self.run(["git", "-C", directory, "checkout", "--detach", base])
        target = directory / module_path
        previous = json.loads((target / "manifest.json").read_text(encoding="utf-8")) if (target / "manifest.json").exists() else None
        next_manifest = json.loads(files["manifest.json"])
        if previous and tuple(map(int, next_manifest["version"].split("."))) <= tuple(map(int, previous["version"].split("."))):
            raise ValueError("升级版本号必须高于已安装版本")
        blockers = []
        if previous:
            for key in ("reads", "actions"):
                if set(next_manifest.get(key, [])) - set(previous.get(key, [])):
                    blockers.append(f"新增 {key} 能力需要由平台维护者纳入授权基线")
            for key in ("input_schema", "output_schema"):
                if next_manifest.get(key, {}) != previous.get(key, {}):
                    blockers.append(f"{key} 发生变更，需要连同调用方完成兼容升级")
        # Resolve before recursive removal; only this package's directory may change.
        scope = (directory / MODULE_ROOT).resolve()
        resolved = target.resolve()
        if resolved.parent != scope or not resolved.is_relative_to(directory.resolve()):
            raise ValueError("Module checkout escaped its allowed directory")
        if target.exists():
            shutil.rmtree(resolved)
        target.mkdir(parents=True)
        for name, content in files.items():
            (target / name).write_text(content, encoding="utf-8", newline="\n")
        self.run(["git", "-C", directory, "add", "--", module_path])
        changed = self.run(["git", "-C", directory, "diff", "--cached", "--name-only"]).splitlines()
        if not changed or any(not name.startswith(module_path + "/") for name in changed):
            raise ValueError("候选提交必须且只能修改所提交的模块目录")
        self.run(["git", "-C", directory, "-c", "user.name=Zhiyin module platform", "-c", "user.email=modules@local.invalid",
                  "commit", "-m", f"module: {version['project_id']} {version['version']} ({version['channel']})"])
        commit = self.run(["git", "-C", directory, "rev-parse", "HEAD"]).strip()
        ref = f"refs/heads/modules/{version['project_id']}/{version['channel']}/{version['version']}/{commit[:12]}"
        with process_lock(self.root / "source-ref.lock"):
            self.run(["git", "-C", self.repo, "fetch", directory, commit + ":" + ref])
        self.report.update({"effective_base_commit": base, "expected_revision": actual, "source_digest": version["digest"],
                            "rules_version": "3", "changed_files": changed, "release_blockers": blockers, "source_ref": ref})
        self.update(candidate_commit=commit, report=self.report)
        return directory, commit

    def gate(self, name, function):
        self.stage = name
        gate = {"name": name, "status": "running", "message": "执行中"}
        self.report["gates"].append(gate)
        self.update(stage=name, report=self.report)
        start = time.monotonic()
        try:
            value = function()
            gate.update(status="passed", message="通过")
            return value
        except Exception as exc:
            gate.update(status="failed", message=self.redact(str(exc)))
            raise
        finally:
            gate["duration_ms"] = int((time.monotonic() - start) * 1000)
            self.update(report=self.report)

    def validate(self, version):
        self.job = version
        self.report = {"gates": [], "previous_attempts": version["report"].get("previous_attempts", [])}
        self.lost.clear()
        self.stopping.clear()
        pulse = threading.Thread(target=self.heartbeat, daemon=True)
        pulse.start()
        try:
            actual = self.worker_status()
            files = self.gate("contracts", lambda: self.package(version))
            checkout, commit = self.candidate(version, files, actual)
            self.gate("tests", lambda: self.gates(checkout))
            self.gate("build", lambda: self.compose(checkout, commit, "build", "api", "web"))
            dataflow = self.gate("dataflow", lambda: self.acceptance(checkout, commit))
            self.report["dataflow"] = dataflow
            self.report["preview"] = dataflow.get("modules", {})
            self.report["images"] = {name: dataflow["artifacts"][name + "_image"] for name in ("api", "web")}
            self.update(status="passed", stage="configuration_required" if self.report["release_blockers"] else "accepted", report=self.report)
            print(f"Accepted {version['project_id']} {version['version']} {commit}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad package must not stop other developers' work
            if not self.lost.is_set():
                self.report["error"] = self.redact(str(exc))
                self.update(status="failed", stage=self.stage, report=self.report,
                            event={"stage": "failed", "message": self.redact(str(exc))})
            print(self.redact(f"Acceptance failed: {exc}"), flush=True)
        finally:
            self.stopping.set()
            pulse.join(timeout=5)
            self.job = None

    def promote_ready(self, actual):
        for version in self.api("/ready"):
            if version["report"].get("release_blockers"):
                continue
            if version["report"].get("expected_revision", "") != actual:
                # Reassembly performs a directory conflict check and reruns every
                # gate against the newer application composition.
                self.api(f"/versions/{version['id']}/retry", {})
                continue
            try:
                self.api(f"/versions/{version['id']}/release", {})
            except urllib.error.HTTPError as exc:
                if exc.code != 409:
                    raise
                return

    def serve_sources(self, once=False):
        with process_lock(self.root / (self.worker_id + ".lock")):
            while True:
                try:
                    actual = self.worker_status()
                    self.promote_ready(actual)
                    version = self.api("/claim", {})
                    if version:
                        self.validate(version)
                        self.promote_ready(self.worker_status())
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    print(self.redact(f"Source worker waiting: {exc}"), flush=True)
                    if once:
                        raise
                if once:
                    return
                time.sleep(3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    SourceWorker(json.loads(args.config.read_text(encoding="utf-8"))).serve_sources(args.once)
