"""Local release executor. Only an exact Git commit and fixed actions enter this process.

Configuration points to a trusted repository, a private staging env file and workbench URL.
The web application has no Docker socket. Logs redact all configured secret values.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import http.client
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request


def read_env(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def request(base, path, *, token="", body=None, method=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base.rstrip('/') + path, headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
        method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        value = json.load(response)
    if "code" in value:
        if value["code"]:
            raise RuntimeError(value.get("message", "请求失败"))
        return value.get("data")
    return value


@contextlib.contextmanager
def process_lock(path: Path):
    """OS-held lock survives neither crashes nor reboots; never steal a live lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


class Executor:
    request = staticmethod(request)

    def __init__(self, config: dict):
        self.config = config
        self.repo = Path(config["repository"]).resolve()
        self.root = Path(config["state_directory"]).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.compose_file = Path(config["compose_file"]).resolve()
        self.env_file = Path(config["staging_env_file"]).resolve()
        self.env = read_env(self.env_file)
        control = read_env(Path(config["workbench_env_file"]))
        self.token = control["ZHIYIN_EXECUTOR_TOKEN"]
        self.base = config.get("workbench_url", "http://127.0.0.1:8014")
        self.target = "http://127.0.0.1:8015"
        self.web = "http://127.0.0.1:5175"
        self.project = "zhiyin-module-staging"
        self.secrets = [v for k, v in {**control, **self.env}.items() if any(s in k for s in ("KEY", "SECRET", "PASSWORD", "TOKEN")) and len(v) >= 6]
        self.job = None
        self.lost = threading.Event()
        self.stopping = threading.Event()
        self.previous = ""

    def redact(self, text, *, truncate=True):
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        return text[-18000:] if truncate else text

    def update(self, **values):
        return request(self.base, f"/api/v1/developer/executor/{self.job['id']}", token=self.token,
                       body={"lease": self.job["lease"], **values})

    def assert_authorized(self):
        """Revoking an uploaded project's trust prevents activation, but not recovery."""
        if not self.job or not self.job.get("result", {}).get("version_id"):
            return
        value = request(self.base, f"/api/v1/developer/executor/{self.job['id']}/authorization", token=self.token)
        if value.get("allowed") is not True:
            raise RuntimeError(value.get("reason") or "组件发布授权已撤销")

    def log(self, stage, message):
        message = self.redact(message)
        self.update(stage=stage, event={"stage": stage, "message": message})
        print(f"[{stage}] {message[-1500:]}", flush=True)

    def heartbeat(self):
        while not self.stopping.wait(20):
            try:
                self.update()
            except Exception:
                self.lost.set()
                return

    def run(self, args, *, cwd=None, extra_env=None, timeout=1200, capture_full=False):
        if self.lost.is_set():
            raise RuntimeError("执行租约失效，已停止后续操作")
        environment = {**os.environ, **(extra_env or {}), "PYTHONUTF8": "1"}
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen([str(x) for x in args], cwd=cwd, env=environment,
                stdout=log, stderr=subprocess.STDOUT, shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            started = time.monotonic()
            while process.poll() is None:
                if self.lost.wait(.5) or time.monotonic() - started > timeout:
                    process.kill()
                    process.wait()
                    raise RuntimeError("执行器租约失效或命令超时")
            log.seek(0)
            output = log.read().decode("utf-8", errors="replace")
        if process.returncode:
            self.save_log(output)
            raise RuntimeError(f"命令失败 ({process.returncode}): {self.redact(output)}")
        self.save_log(output)
        return self.redact(output, truncate=not capture_full)

    def save_log(self, output):
        if self.job:
            directory = self.root / "logs"
            directory.mkdir(exist_ok=True)
            with (directory / f"{self.job['id']}.log").open("a", encoding="utf-8") as stream:
                stream.write(self.redact(output, truncate=False) + "\n")

    def compose(self, checkout, revision, *args):
        # Environment identity, ports and project are fixed by the executor, never by a job.
        env = {**self.env, "PLATFORM_ENV": "staging", "PLATFORM_WEB_PORT": "5175", "PLATFORM_API_PORT": "8015",
               "PLATFORM_REVISION": revision, "ZHIYIN_EXECUTOR_TOKEN": ""}
        return self.run(["docker", "compose", "--project-directory", checkout, "--env-file", self.env_file,
                         "-p", self.project, "-f", self.compose_file, *args], extra_env=env)

    def actual_revision(self):
        try:
            value = request(self.target, "/healthz")
            if value.get("environment") != "staging":
                raise RuntimeError("8015 上运行的不是模块测试环境")
            return value.get("revision", "")
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError):
            return ""

    def checkout(self, revision):
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("必须使用完整 Git SHA")
        directory = self.root / "checkouts" / revision
        if not directory.exists():
            self.run(["git", "-C", self.repo, "cat-file", "-e", revision + "^{commit}"])
            directory.parent.mkdir(parents=True, exist_ok=True)
            self.run(["git", "clone", "--no-hardlinks", "--no-checkout", self.repo, directory])
        # Keep verified historical checkouts usable for recovery even when the
        # development repository has moved on or a branch was removed.
        self.run(["git", "-C", directory, "cat-file", "-e", revision + "^{commit}"])
        self.run(["git", "-C", directory, "config", "core.autocrlf", "false"])
        # Windows 上 260 字符路径上限会让 checkout 直接失败（实测报
        # `fatal: cannot create directory ... Filename too long`），而模块目录本身就很深。
        # 放宽的是路径处理，不动内容；Linux/CI 上设不设都一样。
        self.run(["git", "-C", directory, "config", "core.longpaths", "true"])
        self.run(["git", "-C", directory, "checkout", "--detach", revision])
        self.run(["git", "-C", directory, "checkout-index", "--force", "--all"])
        actual = self.run(["git", "-C", directory, "rev-parse", "HEAD"]).strip()
        if actual != revision:
            raise RuntimeError("检出版本不一致")
        return directory

    def gates(self, checkout):
        """Run checks against this commit in containers; retain the user's existing runtime."""
        self.log("checking", "执行后端测试、模块测试、架构守卫及契约检查")
        template = checkout / "zhiyin-src" / "template"
        # Source-worker tests exercise real commits, ancestry and conflict checks.
        # Git belongs in this disposable test container, not the application image.
        command = (
            "apt-get update -qq && apt-get install -y -qq --no-install-recommends git && "
            "cp -a /source/. /workspace/ && cd /workspace/zhiyin-src/template && "
            "pip install -e '.[dev]' >/tmp/install.log 2>&1 && "
            "python -m pytest -q --import-mode=importlib && python -m ruff check . && "
            "python scripts/export_openapi.py --check && python scripts/module_cli.py check && "
            "ZHIYIN_USE_REMOTE_LLM=1 ZHIYIN_LLM_API_KEY=ci-placeholder python -m zhiyin_boot --check --phase=1"
        )
        name = "zhiyin-module-check-" + self.job["id"]
        # A crashed docker CLI may leave its check container alive. The single executor
        # owns this job name; remove that stale container before resuming the gate.
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log("checking", self.run(["docker", "run", "--rm", "--name", name, "--label", "zhiyin.module.check=true",
            "-v", f"{checkout}:/source:ro", "-w", "/workspace", "python:3.11-slim", "sh", "-c", command]))
        self.log("checking", "执行前端类型检查、构建和 API 类型一致性检查")
        frontend = "cp -a /source/. /workspace/ && cd /workspace/zhiyin-web && npm ci --no-audit --no-fund && cp src/api/types.ts /tmp/api-types.ts && npm run gen:api && cmp src/api/types.ts /tmp/api-types.ts && npm run build"
        self.log("checking", self.run(["docker", "run", "--rm", "--name", name, "--label", "zhiyin.module.check=true",
            "-v", f"{template}:/source:ro", "-w", "/workspace", "node:22-alpine", "sh", "-c", frontend]))

    def wait_healthy(self, revision):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.lost.is_set():
                raise RuntimeError("执行租约失效")
            try:
                value = request(self.web, "/healthz", timeout=3)
                frontend = request(self.web, "/version.json", timeout=3)
                if value.get("status") == "ok" and value.get("revision") == revision and value.get("environment") == "staging" and frontend.get("revision") == revision:
                    return
            except (urllib.error.URLError, TimeoutError, ValueError, http.client.HTTPException, OSError):
                pass
            time.sleep(2)
        raise RuntimeError("测试环境健康检查未通过，或前后端版本不一致")

    def smoke(self, checkout, revision):
        account = self.env.get("PLATFORM_SMOKE_ACCOUNT", "admin")
        password = self.env["PLATFORM_ACCOUNT_PASSWORD"]
        self.log("smoke", self.compose(checkout, revision, "exec", "-T", "-e", "PLATFORM_ACCOUNT_PASSWORD",
            "api", "python", "scripts/module_admin.py", account, "--role", "admin", "--seed"))
        login = request(self.web, "/api/v1/app/auth/login", body={"account": account, "password": password})
        token = login["token"]
        current_policies = request(self.base, "/api/v1/developer/executor/configuration", token=self.token)
        installed = request(self.web, "/api/v1/developer/modules", token=token)
        for module in installed:
            mid = module["manifest"]["id"]
            if mid in current_policies:
                policy = current_policies[mid]
                policy["revision"] = module["policy"]["revision"]
                # Exact submitted manifests must support these grants; mismatch blocks activation.
                request(self.web, f"/api/v1/developer/modules/{mid}/policy", token=token, body=policy, method="PUT")
        for module in request(self.web, "/api/v1/app/modules", token=token):
            request(self.web, f"/api/v1/app/modules/{module['manifest']['id']}/data", token=token)
        request(self.web, "/api/v1/app/plan/action", token=token)
        report = request(self.web, "/api/v1/developer/checks", token=token, body={})
        if not report["passed"]:
            raise RuntimeError("部署后模块检查失败")
        self.log("smoke", "登录、模块数据、原有计划接口、部署后模块检查全部通过")

    def bluegreen(self):
        spec = importlib.util.spec_from_file_location("zhiyin_host_bluegreen", Path(__file__).with_name("module_bluegreen.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.BlueGreenRollout(self)

    def acceptance(self, checkout: Path, revision: str) -> dict:
        """Verify built artifacts against temporary real data services, without routing traffic."""
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("必须使用完整 Git SHA")
        script = Path(checkout) / "zhiyin-src/template/scripts/module_dataflow_acceptance.py"
        if not script.is_file():
            raise ValueError("候选版本缺少平台数据流验收脚本")
        rollout = self.bluegreen()
        artifacts = rollout.images(revision)
        return {**rollout.dataflow_gate(artifacts), "artifacts": artifacts}

    def execute(self, job):
        strategy = self.config.get("rollout_strategy", "replace")
        if strategy == "blue_green":
            return self.bluegreen().execute(job)
        if strategy != "replace":
            raise ValueError("rollout_strategy must be replace or blue_green")
        self.job = job
        self.stopping.clear()
        self.lost.clear()
        heartbeat = threading.Thread(target=self.heartbeat, daemon=True)
        heartbeat.start()
        journal_path = self.root / "deployment.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else {}
        changed = False
        checkout = None
        try:
            self.assert_authorized()
            actual = self.actual_revision()
            self.log("reconcile", f"核对运行环境：{actual or '尚未运行'}；目标：{job['commit']}")
            self.previous = job["result"].get("previous_revision", journal.get("current", actual))
            self.update(result={"previous_revision": self.previous})
            checkout = self.checkout(job["commit"])
            if job["kind"] == "rollback":
                successful = journal.get("successful", [])
                if job["commit"] not in successful:
                    raise ValueError("只能恢复曾经成功发布的版本")
            else:
                self.assert_authorized()
                self.gates(checkout)
                if job["kind"] == "check":
                    self.update(status="succeeded", stage="checked", result={"checked_revision": job["commit"]})
                    return
                self.assert_authorized()
                self.log("building", self.compose(checkout, job["commit"], "build", "api", "web"))
            self.log("deploying", "启动目标版本的独立测试环境")
            self.assert_authorized()
            changed = True
            self.update(result={"deployment_started": True})
            self.compose(checkout, job["commit"], "up", "-d", "--no-build", "--remove-orphans")
            self.wait_healthy(job["commit"])
            self.smoke(checkout, job["commit"])
            journal = {"current": job["commit"], "previous": self.previous,
                       "successful": list(dict.fromkeys([*journal.get("successful", []), job["commit"]]))}
            temporary = journal_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(journal), encoding="utf-8")
            temporary.replace(journal_path)
            self.update(status="succeeded", stage="complete", result={"installed_revision": job["commit"], "url": self.web})
        except Exception as exc:
            if self.lost.is_set():
                # The next lease owner reconciles the durable deployment_started flag and actual containers.
                print("Lease lost; environment will be reconciled by the next executor.", flush=True)
                return
            self.log("failed", str(exc))
            changed = changed or bool(job["result"].get("deployment_started"))
            if changed and self.previous and re.fullmatch(r"[a-f0-9]{40}", self.previous):
                try:
                    previous_checkout = self.checkout(self.previous)
                    self.log("recovering", f"恢复上一应用版本 {self.previous}")
                    self.compose(previous_checkout, self.previous, "up", "-d", "--no-build", "--remove-orphans")
                    self.wait_healthy(self.previous)
                    self.update(status="rolled_back", stage="recovered", result={"installed_revision": self.previous, "url": self.web})
                except Exception as recovery:
                    self.log("recovery_failed", str(recovery))
                    self.update(status="failed", stage="recovery_failed")
            else:
                if changed and checkout is not None:
                    try:
                        self.compose(checkout, job["commit"], "stop", "api", "web")
                    except Exception as cleanup:
                        self.log("cleanup_failed", str(cleanup))
                self.update(status="failed", stage="failed")
        finally:
            self.stopping.set()
            heartbeat.join(timeout=5)
            subprocess.run(["docker", "rm", "-f", "zhiyin-module-check-" + job["id"]],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def serve(self, once=False):
        with process_lock(self.root / "executor.lock"):
            last_error = ""
            while True:
                try:
                    job = request(self.base, "/api/v1/developer/executor/claim", token=self.token, body={})
                except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
                    if once:
                        raise
                    # Never print response bodies, headers or URLs containing credentials.
                    error = type(exc).__name__ + (" HTTP " + str(exc.code) if isinstance(exc, urllib.error.HTTPError) else "")
                    if error != last_error:
                        print("Release queue unavailable: " + error + "; retrying every 3 seconds", flush=True)
                        last_error = error
                    time.sleep(3)
                    continue
                if last_error:
                    print("Release queue connection restored", flush=True)
                    last_error = ""
                if job:
                    self.execute(job)
                if once:
                    return
                time.sleep(3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    Executor(json.loads(args.config.read_text(encoding="utf-8"))).serve(args.once)
