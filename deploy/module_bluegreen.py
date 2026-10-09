"""Whole-application blue/green rollout on the existing staging data services.

This host tool never installs an uploaded module in its own container. Candidate
acceptance uses temporary databases; blue/green share the existing staging data.
Initial migration is explicit because the old application owns ports 5175/8015.
"""
from __future__ import annotations

import argparse
import copy
import http.client
import importlib.util
import json
import os
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).resolve().parent
SLOTS = ("blue", "green")
REVISION = re.compile(r"^[a-f0-9]{40}$")
IMAGE = re.compile(r"^sha256:[a-f0-9]{64}$")
PORTS = {"blue": {"web": 5176, "api": 8016}, "green": {"web": 5177, "api": 8017}}
INCOMPLETE = "蓝绿入口尚未初始化，请先执行 prepare-migration 和 activate-migration；不会自动停止原服务"


def atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def compose_spec():
    """JSON is valid YAML; this source generates the checked-in Compose file."""
    environment = {
        "ZHIYIN_ENV": "docker", "ZHIYIN_MODULE_ENV": "staging", "ZHIYIN_EXECUTOR_TOKEN": "",
        "ZHIYIN_RUN_BACKGROUND_WORKERS": "0", "ZHIYIN_USE_POSTGRES": "1",
        "ZHIYIN_POSTGRES_DSN": "postgresql://zhiyin:${PLATFORM_DB_PASSWORD:?Set PLATFORM_DB_PASSWORD}@postgres:5432/zhiyin",
        "ZHIYIN_USE_REDIS": "1", "ZHIYIN_REDIS_URL": "redis://redis:6379/0",
        "ZHIYIN_AUTH_JWT_SECRET": "${ZHIYIN_AUTH_JWT_SECRET:?Set ZHIYIN_AUTH_JWT_SECRET}",
        "ZHIYIN_USE_REMOTE_LLM": "1", "ZHIYIN_LLM_API_KEY": "${DASHSCOPE_API_KEY:?Set DASHSCOPE_API_KEY}",
        "ZHIYIN_LLM_BASE_URL": "${DASHSCOPE_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}",
        "ZHIYIN_LLM_MODEL": "qwen-flash", "ZHIYIN_USE_REMOTE_EMBEDDING": "1",
        "ZHIYIN_EMBEDDING_PROVIDER": "dashscope_embed", "ZHIYIN_EMBEDDING_API_KEY": "${DASHSCOPE_API_KEY}",
        "ZHIYIN_EMBEDDING_BASE_URL": "${DASHSCOPE_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}",
        "ZHIYIN_EMBEDDING_MODEL": "text-embedding-v4",
    }
    health = {"test": ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()"],
        "interval": "3s", "timeout": "3s", "retries": 40, "start_period": "10s"}
    services = {}
    for slot in SLOTS:
        upper = slot.upper()
        services[f"api_{slot}"] = {
            "image": "${PLATFORM_" + upper + "_API_IMAGE:-zhiyin-platform-api:uninitialized}",
            "environment": copy.deepcopy(environment),
            "ports": [f"127.0.0.1:${{PLATFORM_{upper}_API_PORT:-{PORTS[slot]['api']}}}:8000"],
            "networks": ["shared"], "restart": "unless-stopped", "healthcheck": health,
        }
        services[f"web_{slot}"] = {
            "image": "${PLATFORM_" + upper + "_WEB_IMAGE:-zhiyin-platform-web:uninitialized}",
            "environment": {"PLATFORM_SLOT_API": f"api_{slot}"},
            "ports": [f"127.0.0.1:${{PLATFORM_{upper}_WEB_PORT:-{PORTS[slot]['web']}}}:80"],
            "volumes": ["${PLATFORM_SLOT_NGINX_TEMPLATE:?Set template path}:/etc/nginx/templates/default.conf.template:ro"],
            "depends_on": {f"api_{slot}": {"condition": "service_healthy"}},
            "networks": ["shared"], "restart": "unless-stopped",
        }
    services["background"] = {
        "image": "${PLATFORM_BACKGROUND_API_IMAGE:-zhiyin-platform-api:uninitialized}",
        "environment": {**environment, "ZHIYIN_RUN_BACKGROUND_WORKERS": "1"},
        "networks": ["shared"], "restart": "unless-stopped", "healthcheck": health,
    }
    services["gateway"] = {
        "image": "nginx:1.27-alpine", "ports": ["127.0.0.1:5175:80", "127.0.0.1:8015:8000"],
        "volumes": ["${PLATFORM_GATEWAY_CONFIG_DIR:?Set gateway path}:/etc/nginx/conf.d:ro"],
        "networks": ["shared"], "restart": "unless-stopped", "stop_grace_period": "190s",
    }
    services["acceptance_postgres"] = {
        "image": "pgvector/pgvector:pg16", "profiles": ["acceptance"],
        "environment": {"POSTGRES_USER": "zhiyin", "POSTGRES_DB": "zhiyin",
            "POSTGRES_PASSWORD": "${PLATFORM_ACCEPTANCE_DB_PASSWORD:-unused}"},
        "networks": ["acceptance"],
        "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U zhiyin -d zhiyin"],
            "interval": "2s", "timeout": "3s", "retries": 40},
    }
    services["acceptance_redis"] = {
        "image": "redis:7-alpine", "profiles": ["acceptance"], "networks": ["acceptance"],
        "healthcheck": {"test": ["CMD", "redis-cli", "ping"], "interval": "2s", "timeout": "3s", "retries": 40},
    }
    services["acceptance_api"] = {
        "image": "${PLATFORM_ACCEPTANCE_API_IMAGE:-zhiyin-platform-api:uninitialized}",
        "profiles": ["acceptance"], "environment": {
            **environment, "ZHIYIN_MODULE_ENV": "candidate", "ZHIYIN_DATAFLOW_ISOLATED": "1",
            "ZHIYIN_POSTGRES_DSN": "postgresql://zhiyin:${PLATFORM_ACCEPTANCE_DB_PASSWORD:-unused}@acceptance_postgres:5432/zhiyin",
            "ZHIYIN_REDIS_URL": "redis://acceptance_redis:6379/0",
            "ZHIYIN_AUTH_JWT_SECRET": "${PLATFORM_ACCEPTANCE_JWT_SECRET:-unused}",
            "ZHIYIN_LLM_API_KEY": "candidate-check-only", "ZHIYIN_EMBEDDING_API_KEY": "candidate-check-only",
        }, "networks": ["acceptance"], "healthcheck": health,
        "depends_on": {"acceptance_postgres": {"condition": "service_healthy"},
                       "acceptance_redis": {"condition": "service_healthy"}},
    }
    return {"x-generated-by": "python deploy/module_bluegreen.py --write-compose", "services": services,
        "networks": {"shared": {"external": True, "name": "${PLATFORM_SHARED_NETWORK:-zhiyin-module-staging_default}"},
                     "acceptance": {"internal": True}}}


def gateway_config(slot: str, revision: str, generation: int, previous_slot: str | None = None):
    if slot not in SLOTS or previous_slot not in {*SLOTS, None} or not REVISION.fullmatch(revision):
        raise ValueError("Invalid gateway route")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise ValueError("Invalid routing generation")
    marker = json.dumps({"slot": slot, "revision": revision, "generation": generation}, separators=(",", ":"))
    route = f"location = /__platform_route {{ default_type application/json; add_header Cache-Control no-store; return 200 '{marker}'; }}"
    previous_slot = previous_slot or slot
    return f"""# Generated route; recover from deployment.json before changing this file.
resolver 127.0.0.11 valid=5s ipv6=off;
server {{
  listen 80;
  {route}
  location = /version.json {{ proxy_pass http://web_{slot}:80; add_header Cache-Control no-store; }}
  location /api/ {{ proxy_pass http://api_{slot}:8000; proxy_http_version 1.1; proxy_buffering off; proxy_read_timeout 180s; }}
  location = /healthz {{ proxy_pass http://api_{slot}:8000; add_header Cache-Control no-store; }}
  location /assets/ {{ proxy_pass http://web_{slot}:80; proxy_intercept_errors on; error_page 404 = @previous_assets; }}
  location @previous_assets {{ set $previous_web web_{previous_slot}:80; proxy_pass http://$previous_web$request_uri; }}
  location / {{ proxy_pass http://web_{slot}:80; add_header Cache-Control no-cache; }}
}}
server {{
  listen 8000;
  {route}
  location / {{ proxy_pass http://api_{slot}:8000; proxy_http_version 1.1; proxy_buffering off; proxy_read_timeout 180s; }}
}}
"""


class BlueGreenRollout:
    def __init__(self, executor):
        self.ex = executor
        self.root = executor.root / "bluegreen"
        self.root.mkdir(parents=True, exist_ok=True)
        self.gateway = self.root / "gateway"
        self.gateway.mkdir(exist_ok=True)
        self.journal_path = self.root / "deployment.json"
        self.compose_file = Path(executor.config.get("bluegreen_compose_file", HERE / "compose.bluegreen.yml")).resolve()
        self.project = "zhiyin-module-staging-bluegreen"
        self.ports = copy.deepcopy(PORTS)
        for slot in SLOTS:
            for service in ("web", "api"):
                self.ports[slot][service] = int(executor.config.get(f"{slot}_{service}_port", self.ports[slot][service]))
        values = [port for ports in self.ports.values() for port in ports.values()]
        if any(port < 1024 or port > 65535 or port in {5173, 5174, 5175, 8000, 8014, 8015} for port in values) or len(set(values)) != 4:
            raise ValueError("蓝绿候选端口必须互不重复，并避开现有项目及固定入口")
        self.drain_seconds = max(190, int(executor.config.get("bluegreen_drain_seconds", 190)))
        self.observation_seconds = max(0, int(executor.config.get("bluegreen_observation_seconds", 10)))
        self.extra_env = {}
        self.compose_overlays = []
        self.workflow_guard = None
        self.journal = self.load()

    def request(self, *args, **kwargs):
        # Importing this tool must not require changing sys.path in test callers.
        return self.ex.request(*args, **kwargs)

    def load(self):
        return json.loads(self.journal_path.read_text(encoding="utf-8")) if self.journal_path.exists() else {}

    def save(self):
        atomic_json(self.journal_path, self.journal)

    def log(self, stage, text):
        if self.ex.job:
            self.ex.log(stage, text)
        else:
            print(f"[{stage}] {self.ex.redact(text)}", flush=True)

    def compose(self, *args, project=None, capture_full=False):
        environment = {**self.ex.env, **self.extra_env,
            "PLATFORM_GATEWAY_CONFIG_DIR": str(self.gateway),
            "PLATFORM_SLOT_NGINX_TEMPLATE": str(HERE / "nginx.slot.conf.template"),
            "PLATFORM_SHARED_NETWORK": self.ex.config.get("bluegreen_shared_network", "zhiyin-module-staging_default")}
        for slot in SLOTS:
            installed = self.journal.get("slots", {}).get(slot, {})
            for service in ("api", "web"):
                environment[f"PLATFORM_{slot.upper()}_{service.upper()}_IMAGE"] = installed.get(f"{service}_image", "zhiyin-platform-api:uninitialized" if service == "api" else "zhiyin-platform-web:uninitialized")
                environment[f"PLATFORM_{slot.upper()}_{service.upper()}_PORT"] = str(self.ports[slot][service])
        active = self.journal.get("slots", {}).get(self.journal.get("active_slot"), {})
        environment["PLATFORM_BACKGROUND_API_IMAGE"] = self.extra_env.get("PLATFORM_BACKGROUND_API_IMAGE", active.get("api_image", "zhiyin-platform-api:uninitialized"))
        files = ["-f", self.compose_file]
        for overlay in self.compose_overlays:
            files.extend(["-f", overlay])
        return self.ex.run(["docker", "compose", "--project-directory", self.ex.repo, "--env-file", self.ex.env_file,
            "-p", project or self.project, *files, *args], extra_env=environment, capture_full=capture_full)

    def slot_url(self, slot, service="web"):
        return f"http://127.0.0.1:{self.ports[slot][service]}"

    def route(self):
        value = self.request(self.ex.web, "/__platform_route", timeout=3)
        if value.get("slot") not in SLOTS or not REVISION.fullmatch(value.get("revision", "")):
            raise RuntimeError("固定入口未返回有效蓝绿路由，拒绝覆盖现有服务")
        if not isinstance(value.get("generation"), int) or value["generation"] < 1:
            raise RuntimeError("固定入口的蓝绿代次无效")
        return value

    def check_expected(self, job, route):
        expected = job.get("result", {}).get("expected_revision")
        if expected and route["revision"] not in {expected, job["commit"]}:
            raise RuntimeError("发布基础版本已变化，请重新装配并验收候选版本")

    def wait_healthy(self, slot, revision, *, public=False, timeout=180):
        web = self.ex.web if public else self.slot_url(slot)
        api = self.ex.target if public else self.slot_url(slot, "api")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.assert_workflow_lock()
            if self.ex.lost.is_set():
                raise RuntimeError("执行租约失效")
            try:
                health = self.request(web, "/healthz", timeout=3)
                direct = self.request(api, "/healthz", timeout=3)
                frontend = self.request(web, "/version.json", timeout=3)
                if all(value.get("status") == "ok" and value.get("revision") == revision and value.get("environment") == "staging" for value in (health, direct)) and frontend.get("revision") == revision:
                    return
            except (OSError, ValueError, RuntimeError, http.client.HTTPException):
                pass
            self.ex.lost.wait(2)
        raise RuntimeError("候选槽健康检查未通过或前后端版本不一致")

    def images(self, revision):
        result = {"revision": revision}
        for service in ("api", "web"):
            image = self.ex.run(["docker", "image", "inspect", "--format", "{{.Id}}", f"zhiyin-platform-{service}:{revision}"]).strip()
            if not IMAGE.fullmatch(image):
                raise RuntimeError("镜像摘要无效")
            result[f"{service}_image"] = image
        return result

    def accepted_artifacts(self, job):
        """Only server-created uploaded-version jobs may reuse accepted artifacts."""
        metadata = job.get("result", {})
        value = metadata.get("accepted_artifacts")
        if (job.get("kind") != "deploy" or metadata.get("rules_version") != "3"
                or not re.fullmatch(r"[a-f0-9]{32}", str(metadata.get("version_id", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(metadata.get("digest", "")))
                or not REVISION.fullmatch(str(metadata.get("expected_revision", "")))
                or not isinstance(value, dict) or value.get("revision") != job["commit"]):
            raise ValueError("上传版本缺少完整且匹配的已验收镜像凭据，拒绝重新构建替代")
        for service in ("api", "web"):
            identifier = value.get(f"{service}_image", "")
            if not isinstance(identifier, str) or not IMAGE.fullmatch(identifier):
                raise ValueError("已验收镜像必须使用完整且不可变的 sha256 摘要")
            actual = self.ex.run(["docker", "image", "inspect", "--format", "{{.Id}}", identifier]).strip()
            if actual != identifier:
                raise ValueError("已验收镜像不存在或摘要不一致，拒绝重新构建替代")
        return {key: value[key] for key in ("revision", "api_image", "web_image")}

    def dataflow_gate(self, images):
        """Never change policies or test data in the active staging database."""
        identifier, lease = self.ex.job["id"], self.ex.job["lease"]
        if not re.fullmatch(r"[a-f0-9]{32}", identifier) or not re.fullmatch(r"[a-f0-9]{32}", lease):
            raise ValueError("候选环境需要有效任务编号及执行租约")
        # A replacement lease must never reconnect to an interrupted lease's
        # PostgreSQL directory with newly generated credentials.
        project = "zhiyin-module-candidate-" + identifier[:16] + "-" + lease[:12]
        browser_python = Path(self.ex.config.get("browser_python", ""))
        if not browser_python.is_absolute() or not browser_python.is_file():
            raise ValueError("请在可信宿主配置中设置安装了 Playwright 的 browser_python 绝对路径；浏览器门禁不可跳过")
        spec = importlib.util.spec_from_file_location("candidate_module_browser_gate", HERE / "module_browser_gate.py")
        browser_gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(browser_gate)
        evidence = self.ex.root / "acceptance" / "jobs" / identifier / lease
        evidence.mkdir(parents=True, exist_ok=True)
        overlay = evidence / "browser.compose.json"
        atomic_json(overlay, browser_gate.candidate_web_overlay())
        template = evidence / "browser.nginx.template"
        template.write_text(browser_gate.candidate_nginx_template(), encoding="utf-8")
        port = browser_gate.allocate_web_port([value for ports in self.ports.values() for value in ports.values()])
        original_overlays = self.compose_overlays
        self.compose_overlays = [*original_overlays, overlay]
        self.extra_env.update(PLATFORM_ACCEPTANCE_API_IMAGE=images["api_image"],
            PLATFORM_ACCEPTANCE_DB_PASSWORD=uuid4().hex, PLATFORM_ACCEPTANCE_JWT_SECRET=uuid4().hex + uuid4().hex,
            PLATFORM_ACCEPTANCE_WEB_IMAGE=images["web_image"], PLATFORM_ACCEPTANCE_WEB_PORT=str(port),
            PLATFORM_BROWSER_NGINX_TEMPLATE=str(template))
        self.ex.secrets.extend([self.extra_env["PLATFORM_ACCEPTANCE_DB_PASSWORD"], self.extra_env["PLATFORM_ACCEPTANCE_JWT_SECRET"]])
        self.log("dataflow", "在独立候选数据库中验收全部模块，包括停用模块和纯技能")
        try:
            self.compose("up", "-d", "acceptance_api", project=project)
            self.wait_service("acceptance_api", project=project)
            self.compose("exec", "-T", "acceptance_api", "python", "-c",
                "import json,sys,urllib.request; value=json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz')); assert value.get('revision')==sys.argv[1] and value.get('environment')=='candidate' and value.get('status')=='ok', value",
                images["revision"], project=project)
            output = self.compose("exec", "-T", "acceptance_api", "python", "scripts/module_dataflow_acceptance.py",
                "--output", "/tmp/module-dataflow-report.json", project=project, capture_full=True)
            self.log("dataflow", output)
            report = json.loads(self.compose("exec", "-T", "acceptance_api", "cat", "/tmp/module-dataflow-report.json",
                project=project, capture_full=True))
            if report.get("passed") is not True:
                raise RuntimeError("候选版本未通过真实数据流验收")
            # Missing inputs/revision from older reports cannot satisfy this gate.
            browser_gate.dataflow_contract(report, images["revision"])
            dataflow_path = evidence / "dataflow.json"
            browser_path = evidence / "browser.json"
            atomic_json(dataflow_path, report)
            password = uuid4().hex + uuid4().hex
            self.ex.secrets.append(password)
            self.extra_env["PLATFORM_ACCOUNT_PASSWORD"] = password
            self.compose("exec", "-T", "-e", "PLATFORM_ACCOUNT_PASSWORD", "acceptance_api", "python", "scripts/module_admin.py",
                report["preview_user_id"], "--role", "admin", "--reset-password", project=project)
            self.compose("up", "-d", "--no-build", "acceptance_web", project=project)
            self.log("browser", "在候选独立网页中检查全部模块的正常、空数据、错误、详情及窄屏；复用数据流合成账号")
            try:
                self.ex.run([browser_python, HERE / "module_browser_gate.py", "--url", f"http://127.0.0.1:{port}",
                    "--revision", images["revision"], "--dataflow-report", dataflow_path, "--output", browser_path],
                    extra_env={"PYTHONUTF8": "1", "PLATFORM_BROWSER_ACCOUNT": report["preview_user_id"], "PLATFORM_BROWSER_PASSWORD": password}, timeout=660)
                browser = json.loads(browser_path.read_text(encoding="utf-8"))
                browser_gate.validate_browser_result(browser, report, images["revision"])
                report["browser"] = browser
                report.setdefault("gates", []).append({"id": "module_browser", "passed": True, "modules": list(report["modules"])})
                atomic_json(dataflow_path, report)
                self.log("browser", f"浏览器门禁通过；逐项结果及截图保存在 {browser_path}")
            except Exception as exc:  # noqa: BLE001 - Preserve screenshot/report paths for failed uploaded modules.
                report["passed"] = False
                report["browser"] = json.loads(browser_path.read_text(encoding="utf-8")) if browser_path.exists() else {"passed": False, "error": self.ex.redact(str(exc))}
                reason = report["browser"].get("error") or self.ex.redact(str(exc))
                failures = [(mid, check) for mid, item in report["browser"].get("modules", {}).items()
                            for check in item.get("checks", []) if check.get("passed") is not True]
                if failures:
                    mid, check = failures[0]
                    reason = f"{mid}/{check.get('fixture', '?')}/{check.get('viewport', '?')}: {check.get('error') or reason}"
                relative_report = browser_path.relative_to(self.ex.root).as_posix()
                report.setdefault("gates", []).append({"id": "module_browser", "passed": False, "report": relative_report})
                atomic_json(dataflow_path, report)
                self.log("browser_failed", f"{self.ex.redact(reason)}；证据：{relative_report}")
                raise RuntimeError(f"候选浏览器门禁失败：{self.ex.redact(reason)}；结果与截图：{relative_report}") from exc
            return report
        finally:
            # Exact private project only. No shared volumes or staging services belong to it.
            try:
                if not self.ex.lost.is_set():
                    self.compose("--profile", "acceptance", "down", "--remove-orphans", "--volumes", project=project)
                    remaining = self.ex.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"]).strip()
                    if remaining:
                        raise RuntimeError("候选环境清理后仍存在容器，已保留项目和日志供维护者处理")
            finally:
                self.compose_overlays = original_overlays

    def wait_service(self, service, *, project=None):
        deadline = time.monotonic() + 180
        while True:
            container = self.compose("ps", "-q", service, project=project).strip()
            if container:
                status = self.ex.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container]).strip()
                if status == "healthy":
                    return
                if status == "unhealthy":
                    raise RuntimeError(f"服务 {service} 启动失败")
            if time.monotonic() >= deadline or self.ex.lost.wait(2):
                raise RuntimeError(f"服务 {service} 启动超时或执行租约失效")

    def smoke(self, slot):
        """Read the candidate endpoints with its own synthetic account; never copy policies."""
        tag = self.ex.job["id"][:16] if self.ex.job else "migration"
        account = "module_release_" + tag
        password = uuid4().hex + uuid4().hex
        self.ex.secrets.append(password)
        self.extra_env["PLATFORM_ACCOUNT_PASSWORD"] = password
        self.compose("exec", "-T", "-e", "PLATFORM_ACCOUNT_PASSWORD", f"api_{slot}",
            "python", "scripts/module_admin.py", account, "--role", "admin", "--seed", "--reset-password")
        base = self.slot_url(slot)
        login = self.request(base, "/api/v1/app/auth/login", body={"account": account, "password": password})
        token = login["token"]
        modules = self.request(base, "/api/v1/developer/modules", token=token)
        for module in modules:
            if module["effective_enabled"]:
                self.request(base, f"/api/v1/app/modules/{module['manifest']['id']}/data", token=token)
        self.request(base, "/api/v1/app/plan/action", token=token)
        self.log("smoke", f"{slot} 槽独立端口登录、已启用模块及原有计划读取通过；未修改正式模块授权")

    def prepare_route(self, slot, revision, generation, previous_slot):
        (self.gateway / "route.pending").write_text(gateway_config(slot, revision, generation, previous_slot), encoding="utf-8")
        (self.gateway / "validate.pending").write_text("events {}\nhttp { include /etc/nginx/mime.types; include /etc/nginx/conf.d/route.pending; }\n", encoding="utf-8")
        self.compose("run", "--rm", "--no-deps", "--entrypoint", "nginx", "gateway", "-t", "-c", "/etc/nginx/conf.d/validate.pending")

    def assert_workflow_lock(self):
        if self.workflow_guard is not None:
            self.workflow_guard.assert_alive()

    def acquire_workflow_lock(self, slot):
        """Freeze publication and validate every published snapshot in the target DB."""
        spec = importlib.util.spec_from_file_location("deployment_workflow_guard", HERE / "module_workflow_guard.py")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        container = self.compose("ps", "-q", f"api_{slot}").strip()
        guard = helper.WorkflowPublicationGuard(self.ex, container)
        self.workflow_guard = guard
        try:
            report = guard.acquire()
            self.log("workflow_compatibility", f"{len(report['workflows'])} 个已发布工作流与候选版本兼容；持有发布锁直到切流结束")
        except BaseException:
            self.release_workflow_lock()
            raise
        finally:
            if guard.report is not None and self.ex.job:
                evidence = self.ex.root / "acceptance" / "jobs" / self.ex.job["id"] / self.ex.job["lease"]
                atomic_json(evidence / f"workflow-compatibility-{slot}.json", guard.report)

    def release_workflow_lock(self):
        guard, self.workflow_guard = self.workflow_guard, None
        if guard is not None:
            guard.close()

    def fence_workflow_revision(self, revision):
        if self.workflow_guard is None:
            raise RuntimeError("切流需要持有工作流发布锁")
        self.workflow_guard.fence(revision)

    def switch(self, slot, revision, generation, previous_slot, *, start=False):
        self.assert_workflow_lock()
        self.prepare_route(slot, revision, generation, previous_slot)
        self.assert_workflow_lock()
        os.replace(self.gateway / "route.pending", self.gateway / "default.conf")
        if start:
            self.compose("up", "-d", "gateway")
        else:
            self.compose("exec", "-T", "gateway", "nginx", "-s", "reload")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self.assert_workflow_lock()
            if self.ex.lost.is_set():
                raise RuntimeError("执行租约失效")
            try:
                actual = self.route()
                if actual == {"slot": slot, "revision": revision, "generation": generation}:
                    return
            except (OSError, ValueError, RuntimeError, http.client.HTTPException):
                pass
            self.ex.lost.wait(.25)
        raise RuntimeError("网关未确认目标版本，进入恢复流程")

    def background(self, slot):
        self.assert_workflow_lock()
        self.log("background", "有序更新唯一后台实例，期间调度短暂暂停")
        self.extra_env["PLATFORM_BACKGROUND_API_IMAGE"] = self.journal["slots"][slot]["api_image"]
        self.compose("up", "-d", "--no-build", "background")
        self.wait_service("background")
        self.assert_workflow_lock()

    def finish(self, slot, revision, previous_slot, generation):
        self.assert_workflow_lock()
        self.journal.update(active_slot=slot, active_revision=revision, generation=generation,
            previous_slot=previous_slot, previous_revision=self.journal.get("slots", {}).get(previous_slot, {}).get("revision"),
            successful=list(dict.fromkeys([*self.journal.get("successful", []), revision])),
            previous_reusable_after=time.time() + self.drain_seconds, pending=None)
        self.save()

    def reconcile(self):
        if not self.journal.get("active_slot"):
            raise RuntimeError(INCOMPLETE)
        try:
            actual = self.route()
        except (OSError, http.client.HTTPException):
            if not (self.gateway / "default.conf").is_file():
                raise RuntimeError("缺少已持久化的网关配置，拒绝猜测恢复") from None
            self.compose("up", "-d", "gateway")
            actual = self.route()
        known = {(self.journal["active_slot"], self.journal["active_revision"])}
        pending = self.journal.get("pending") or {}
        if pending.get("target_slot"):
            known.add((pending["target_slot"], pending["target_revision"]))
        if (actual["slot"], actual["revision"]) not in known:
            raise RuntimeError("网关实际版本与发布日志不一致，请核对后恢复，拒绝覆盖未知版本")
        return actual

    def wait_drained(self, slot):
        if slot != self.journal.get("previous_slot"):
            return
        until = self.journal.get("previous_reusable_after", 0)
        if until > time.time():
            self.log("draining", "等待上一槽连接排空，期间当前版本继续服务")
        while time.time() < until:
            if self.ex.lost.wait(min(1, until - time.time())):
                raise RuntimeError("执行租约失效")
        # A long SSE stream may remain open beyond the initial quiet period.
        # Never overwrite its slot while old Nginx workers are still draining.
        deadline = time.monotonic() + max(30, int(self.ex.config.get("bluegreen_max_drain_wait_seconds", 600)))
        while "worker process is shutting down" in self.compose("exec", "-T", "gateway", "ps", "-o", "args"):
            if time.monotonic() >= deadline:
                raise RuntimeError("上一槽仍有未结束连接，保留两槽并拒绝本次发布，请稍后重试")
            if self.ex.lost.wait(2):
                raise RuntimeError("执行租约失效")

    def execute(self, job):
        self.ex.job = job
        self.ex.stopping.clear()
        self.ex.lost.clear()
        heartbeat = threading.Thread(target=self.ex.heartbeat, daemon=True)
        heartbeat.start()
        pending = None
        try:
            self.ex.assert_authorized()
            if not REVISION.fullmatch(job["commit"]):
                raise ValueError("必须使用完整 Git SHA")
            actual = self.reconcile()
            self.check_expected(job, actual)
            saved = self.journal.get("pending") or {}
            if saved and saved.get("job_id") != job["id"]:
                raise RuntimeError("存在另一任务尚未恢复的切流记录")
            metadata = job.get("result", {})
            accepted = self.accepted_artifacts(job) if metadata.get("version_id") or "accepted_artifacts" in metadata else None
            if actual["revision"] == job["commit"] and job["kind"] != "check":
                if accepted is not None and any(self.journal.get("slots", {}).get(actual["slot"], {}).get(key) != value
                                                for key, value in accepted.items()):
                    raise RuntimeError("当前同一提交运行的是另一组镜像，不能认定已验收镜像上线")
                previous = saved.get("previous_slot", self.journal.get("previous_slot"))
                self.wait_healthy(actual["slot"], job["commit"], public=True)
                self.smoke(actual["slot"])
                self.acquire_workflow_lock(actual["slot"])
                self.fence_workflow_revision(job["commit"])
                self.background(actual["slot"])
                self.finish(actual["slot"], job["commit"], previous, actual["generation"])
                self.ex.update(status="succeeded", stage="reconciled", result={"installed_revision": job["commit"], "url": self.ex.web})
                return
            active = actual["slot"]
            target = "green" if active == "blue" else "blue"
            self.wait_drained(target)
            checkout = self.ex.checkout(job["commit"])
            if accepted is not None:
                artifacts = accepted
                self.log("accepted_artifacts", "使用上传流水线已经通过完整验收的不可变镜像；不重复构建")
            elif job["kind"] == "rollback":
                if job["commit"] not in self.journal.get("successful", []):
                    raise ValueError("只能回退到已成功发布的版本")
                artifacts = next((value for value in self.journal.get("artifacts", {}).values() if value.get("revision") == job["commit"]), None)
                if artifacts is None:
                    raise RuntimeError("缺少已验证镜像摘要，禁止重新构建冒充历史版本")
            else:
                self.ex.assert_authorized()
                self.ex.gates(checkout)
                self.ex.assert_authorized()
                self.log("building", self.ex.compose(checkout, job["commit"], "build", "api", "web"))
                report = self.ex.acceptance(checkout, job["commit"])
                artifacts = report["artifacts"]
                if job["kind"] == "check":
                    self.ex.update(status="succeeded", stage="dataflow_checked", result={"checked_revision": job["commit"], "artifacts": artifacts, "dataflow": report})
                    return
            self.journal.setdefault("slots", {})[target] = artifacts
            self.journal.setdefault("artifacts", {})[job["commit"]] = artifacts
            pending = {"job_id": job["id"], "target_slot": target, "target_revision": job["commit"],
                "previous_slot": active, "previous_revision": actual["revision"], "generation": actual["generation"] + 1,
                "phase": "starting"}
            self.journal["pending"] = pending
            self.save()
            self.log("candidate_start", f"启动未激活的 {target} 槽；{active} 槽继续提供服务")
            self.compose("up", "-d", "--no-build", f"api_{target}", f"web_{target}")
            self.wait_healthy(target, job["commit"])
            self.smoke(target)
            self.acquire_workflow_lock(target)
            current = self.reconcile()
            self.check_expected(job, current)
            if current != actual:
                raise RuntimeError("检查期间入口发生变化，拒绝切流")
            self.ex.assert_authorized()
            pending["phase"] = "switching"
            self.save()
            self.switch(target, job["commit"], pending["generation"], active)
            self.fence_workflow_revision(job["commit"])
            pending["phase"] = "observing"
            self.save()
            self.wait_healthy(target, job["commit"], public=True)
            self.background(target)
            until = time.monotonic() + self.observation_seconds
            while time.monotonic() < until:
                self.assert_workflow_lock()
                if self.ex.lost.wait(min(2, until - time.monotonic())):
                    raise RuntimeError("执行租约失效")
                self.wait_healthy(target, job["commit"], public=True, timeout=10)
            self.finish(target, job["commit"], active, pending["generation"])
            self.ex.update(status="succeeded", stage="complete", result={"installed_revision": job["commit"],
                "url": self.ex.web, "slot": target, "artifacts": artifacts})
        except Exception as exc:  # noqa: BLE001 - Every deployment failure must enter recovery.
            if self.ex.lost.is_set():
                print("Lease lost; preserve both slots and the pending journal for recovery.", flush=True)
                return
            self.log("failed", str(exc))
            pending = pending or self.journal.get("pending")
            try:
                if pending and pending.get("job_id") == job["id"] and pending.get("phase") in {"switching", "observing"}:
                    old = pending["previous_slot"]
                    try:
                        self.assert_workflow_lock()
                    except RuntimeError:
                        self.release_workflow_lock()
                    if self.workflow_guard is None:
                        self.acquire_workflow_lock(old)
                    self.wait_healthy(old, pending["previous_revision"])
                    self.switch(old, pending["previous_revision"], pending["generation"] + 1, pending["target_slot"])
                    self.fence_workflow_revision(pending["previous_revision"])
                    self.background(old)
                    self.wait_healthy(old, pending["previous_revision"], public=True)
                    self.finish(old, pending["previous_revision"], pending["target_slot"], pending["generation"] + 1)
                    self.ex.update(status="rolled_back", stage="recovered", result={"installed_revision": pending["previous_revision"], "url": self.ex.web})
                else:
                    if pending and pending.get("job_id") == job["id"]:
                        self.journal["pending"] = None
                        self.save()
                    self.ex.update(status="failed", stage="failed")
            except Exception as recovery:  # noqa: BLE001 - Preserve a failed recovery for the next operator.
                self.log("recovery_failed", str(recovery))
                self.ex.update(status="failed", stage="recovery_failed")
        finally:
            try:
                self.release_workflow_lock()
            finally:
                self.ex.stopping.set()
                heartbeat.join(timeout=5)

    def prepare_migration(self, revision):
        previous = self.ex.actual_revision()
        if not REVISION.fullmatch(revision) or not REVISION.fullmatch(previous):
            raise RuntimeError("迁移版本和当前 8015 都必须具有完整版本号")
        if self.journal.get("active_slot"):
            raise RuntimeError("蓝绿已经初始化，无需重复迁移")
        artifacts = self.images(revision)
        self.ex.run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python", artifacts["api_image"],
            "-c", "import inspect; from zhiyin_boot.container import wire_application; assert 'ZHIYIN_RUN_BACKGROUND_WORKERS' in inspect.getsource(wire_application), 'Migration image must support disabling API background workers'"])
        self.journal = {"schema": 1, "slots": {"blue": artifacts}, "artifacts": {revision: artifacts},
            "successful": [], "migration": {"revision": revision, "previous_revision": previous, "phase": "preparing"}}
        self.save()
        self.compose("up", "-d", "--no-build", "api_blue", "web_blue")
        self.wait_healthy("blue", revision)
        self.smoke("blue")
        self.prepare_route("blue", revision, 1, None)
        self.journal["migration"]["phase"] = "prepared"
        self.save()
        self.log("migration_prepared", "蓝槽已预热，原 5175/8015 仍在服务；显式执行 activate-migration 才交接端口")

    def activate_migration(self):
        migration = self.journal.get("migration") or {}
        if migration.get("phase") != "prepared" or self.journal.get("active_slot"):
            raise RuntimeError("请先完成 prepare-migration")
        revision = migration["revision"]
        previous = migration["previous_revision"]
        if self.ex.actual_revision() != previous:
            raise RuntimeError("准备迁移后旧环境版本已改变")
        self.wait_healthy("blue", revision)
        checkout = self.ex.checkout(previous)
        migration["phase"] = "handoff"
        self.save()
        try:
            self.ex.compose(checkout, previous, "stop", "api", "web")
            self.switch("blue", revision, 1, None, start=True)
            self.wait_healthy("blue", revision, public=True)
            self.background("blue")
            migration["phase"] = "complete"
            self.finish("blue", revision, None, 1)
        except Exception:
            self.recover_migration()
            raise

    def recover_migration(self):
        """Explicit recovery also works after the host dies during port handoff."""
        migration = self.journal.get("migration") or {}
        if migration.get("phase") not in {"handoff", "prepared"} or self.journal.get("active_slot"):
            raise RuntimeError("没有待恢复的首次迁移；已完成的蓝绿发布应使用版本回退")
        previous = migration["previous_revision"]
        observed = self.ex.actual_revision()
        if observed and observed not in {previous, migration["revision"]}:
            raise RuntimeError("入口出现未知版本，拒绝停止该服务")
        self.compose("stop", "gateway", "background")
        checkout = self.ex.checkout(previous)
        self.ex.compose(checkout, previous, "up", "-d", "--no-build", "api", "web")
        self.ex.wait_healthy(previous)
        migration["phase"] = "prepared"
        self.save()
        self.log("migration_restored", "首次迁移已恢复原服务，数据库与 Redis 保留不变")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-compose", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("command", choices=["status", "prepare-migration", "activate-migration", "recover-migration"], nargs="?")
    parser.add_argument("--revision")
    args = parser.parse_args()
    if args.write_compose:
        atomic_json(HERE / "compose.bluegreen.yml", compose_spec())
        return
    if not args.config or not args.command:
        parser.error("--config and a command are required")
    spec = importlib.util.spec_from_file_location("bluegreen_host_executor", HERE / "module_executor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    executor = module.Executor(json.loads(args.config.read_text(encoding="utf-8")))
    with module.process_lock(executor.root / "executor.lock"):
        rollout = BlueGreenRollout(executor)
        if args.command == "prepare-migration":
            rollout.prepare_migration(args.revision or "")
        elif args.command == "activate-migration":
            rollout.activate_migration()
        elif args.command == "recover-migration":
            rollout.recover_migration()
        else:
            print(json.dumps({"journal": rollout.journal, "route": rollout.route()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
