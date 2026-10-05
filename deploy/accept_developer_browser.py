"""Browser acceptance against the real isolated 5174/5175 backends, without API interception.

Requires Playwright and Microsoft Edge in the local development environment.
Run --upload-good only after accept_developer_platform.py prepare has produced a
failed bad_version_id. It submits version 0.1.1 through the browser and stores its
ID in the shared lifecycle file; do not run another lifecycle writer concurrently.
Run without that flag after the monitor and verify phases have deployed and
authorized the module. The normal run never uploads or publishes another version.
Run --watch-update before the good upload to watch the real staged deployment
switch, retaining an unsaved workflow name and opening the new version in a tab.
Evidence is written below .platform/acceptance and excludes passwords/tokens.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from module_executor import read_env

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / ".platform" / "acceptance"
LIFECYCLE = DIRECTORY / "developer-v2-lifecycle.json"
WORKBENCH = "http://127.0.0.1:5174"
STAGING = "http://127.0.0.1:5175"


class BrowserAcceptance:
    def __init__(self, args):
        self.args = args
        self.lifecycle_path = args.lifecycle.resolve()
        self.state = json.loads(self.lifecycle_path.read_text(encoding="utf-8"))
        self.project_id = self.state["project_id"]
        self.expected_version = self.state.get("expected_version", "0.1.1")
        assert re.fullmatch(r"[a-z][a-z0-9_]{1,47}", self.project_id), "Invalid lifecycle project ID"
        self.workbench_env = read_env(ROOT / ".platform" / "workbench.env")
        self.staging_env = read_env(ROOT / ".platform" / "staging.env")
        self.secrets = {self.workbench_env["PLATFORM_ACCOUNT_PASSWORD"], self.staging_env["PLATFORM_ACCOUNT_PASSWORD"]}
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        suffix = "-upload" if args.upload_good else "-update" if args.watch_update else "-installed" if args.installed_only else ""
        self.output = DIRECTORY / ("developer-v2-browser" + suffix + ".json")
        self.report = {
            "method": "real browser and real backend; no API interception",
            "mode": "upload-good" if args.upload_good else "watch-update" if args.watch_update else "verify-installed-only" if args.installed_only else "verify-existing-release",
            "project_id": self.project_id,
            "expected_version": self.expected_version,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "checks": [], "passed": False,
            "scope": {"creates_project": False, "uploads_version": args.upload_good,
                      "publishes_release": False, "changes_module_policy": False,
                      "workflow_mode": "fixture, read-only"},
        }
        self.page = None
        self.step = "initialization"
        self.requests: dict[str, list[str]] = {}
        self.errors: dict[str, list[str]] = {}
        self.api_errors: dict[str, list[dict]] = {}
        self.expected_api_errors: dict[str, list[dict]] = {}
        self.version_reads: dict[str, list[str]] = {}
        self.workflow_name = ""
        self.installed_module_version = ""

    def redact(self, value):
        text = str(value)
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "[redacted]")
        return text

    def save(self):
        self.output.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(self, name, **values):
        self.report["checks"].append({"check": name, "passed": True, **values})
        self.save()
        print("PASS", name, flush=True)

    def screenshot(self, name):
        path = DIRECTORY / ("developer-v2-browser-" + name + ".png")
        self.page.screenshot(path=str(path), full_page=True)
        return path.name

    @staticmethod
    def data(response):
        value = response.json()
        assert response.ok and value.get("code") == 0, (
            f"Backend rejected {urlsplit(response.url).path}: HTTP {response.status}; "
            f"{value.get('message', 'invalid response')}"
        )
        return value["data"]

    def get(self, path):
        """Read-only checks complement browser actions; mutations use visible UI."""
        token = self.page.evaluate("localStorage.getItem('zhiyin_token')")
        if token:
            self.secrets.add(token)
        origin = urlsplit(self.page.url)
        response = self.page.request.get(
            f"{origin.scheme}://{origin.netloc}/api/v1{path}",
            headers={"Authorization": "Bearer " + (token or "")},
        )
        return self.data(response)

    def observe(self, page, environment):
        from playwright.sync_api import Error as PlaywrightError

        self.requests[environment], self.errors[environment], self.api_errors[environment] = [], [], []
        self.version_reads[environment] = []
        page.on("request", lambda req: self.requests[environment].append(urlsplit(req.url).path))
        page.on("pageerror", lambda error: self.errors[environment].append(self.redact(error)))

        def response_error(response):
            if urlsplit(response.url).path == "/version.json":
                try:
                    revision = response.json().get("revision")
                    if isinstance(revision, str) and revision:
                        self.version_reads[environment].append(revision)
                except (ValueError, PlaywrightError) as exc:
                    self.report.setdefault("response_read_errors", []).append({
                        "environment": environment, "path": "/version.json", "error": self.redact(exc),
                    })
                return
            if "/api/v1/" not in response.url:
                return
            try:
                if "application/json" not in response.headers.get("content-type", ""):
                    return
                value = response.json()
                if response.status >= 400 or value.get("code", 0):
                    self.api_errors[environment].append({
                        "path": urlsplit(response.url).path, "http_status": response.status,
                        "code": value.get("code"), "message": self.redact(value.get("message", "")),
                    })
            except (ValueError, PlaywrightError):
                # An abandoned response during navigation cannot be decoded;
                # explicit UI assertions and request failures still determine results.
                return

        page.on("response", response_error)

    def login(self, browser, environment):
        from playwright.sync_api import expect

        self.step = environment + "_login"
        env = self.workbench_env if environment == "workbench" else self.staging_env
        account = env.get("PLATFORM_DEVELOPER_ACCOUNT", "module_developer") if environment == "workbench" else "admin"
        url = WORKBENCH if environment == "workbench" else STAGING
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = context.new_page()
        self.page = page
        self.observe(page, environment)
        page.goto(url + "/developer")
        page.locator('input[name="account"]').fill(account)
        page.locator('input[name="password"]').fill(env["PLATFORM_ACCOUNT_PASSWORD"])
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/app/auth/login") as login:
            page.get_by_role("button", name="登录并进入", exact=True).click()
        result = self.data(login.value)
        self.secrets.add(result["token"])
        assert result["role"] == ("developer" if environment == "workbench" else "admin"), result["role"]
        page.wait_for_url(url + "/")
        page.goto(url + "/developer")
        expect(page.get_by_role("heading", name="模块开发工作台" if environment == "workbench" else "测试环境模块管理", exact=True)).to_be_visible()
        self.record(environment + "_real_ui_login", account=account, role=result["role"])
        return context

    def download_template(self):
        self.step = "template_download"
        project = next(p for p in self.get("/developer/projects") if p["id"] == self.project_id)
        page = self.page
        page.get_by_role("button", name="开始开发", exact=True).click()
        page.get_by_label(re.compile(r"^模块类型")).select_option("hybrid")
        page.get_by_label("模块编号", exact=True).fill(self.project_id)
        page.get_by_label("模块名称", exact=True).fill(project["name"])
        page.get_by_label("负责人", exact=True).fill(project["owner"])
        with page.expect_download() as event:
            page.get_by_role("button", name="下载开发模板 ZIP", exact=True).click()
        destination = DIRECTORY / (self.project_id + "-browser-template.zip")
        event.value.save_as(str(destination))
        with zipfile.ZipFile(destination) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["id"] == self.project_id and manifest["kind"] == "hybrid"
            assert {"backend.py", "fixtures.json", "test_module.py", "Card.vue", "Detail.vue", "dataflow.json"} <= set(archive.namelist())
        self.record("template_download_through_real_ui", package=destination.name,
                    screenshot=self.screenshot("template"), module_kind=manifest["kind"])
        return destination

    def select_project(self):
        page = self.page
        page.get_by_role("button", name="项目与版本", exact=True).click()
        page.locator('aside[aria-label="项目列表"]').get_by_role("button").filter(has_text=self.project_id).click()
        page.get_by_role("heading", name="上传模块版本", exact=True).wait_for()

    def forms(self, package):
        from playwright.sync_api import expect

        self.step = "project_forms"
        self.select_project()
        page = self.page
        page.get_by_role("button", name="创建模块项目", exact=True).click()
        expect(page.get_by_label("项目编号", exact=True)).to_be_visible()
        screenshot = self.screenshot("project-create-form")
        page.get_by_role("button", name="收起新建", exact=True).click()
        page.get_by_label("模块 ZIP 文件", exact=True).set_input_files(str(package))
        expect(page.get_by_role("button", name="上传并启动自动验收", exact=True)).to_be_enabled()
        self.record("existing_project_and_create_upload_forms", screenshot=screenshot,
                    upload_form_screenshot=self.screenshot("upload-form"),
                    submitted=False, note="Existing lifecycle project reused; creation form inspected, no extra project or version submitted.")

    def upload_good(self, package):
        from playwright.sync_api import expect

        self.step = "upload_good_preconditions"
        assert not self.state.get("good_version_id"), "Good version already recorded; do not submit again"
        bad = self.get("/developer/versions/" + self.state["bad_version_id"])
        assert bad["status"] == "failed" and not bad["release_job_id"], "Bad version must fail before replacement upload"
        assert any(gate["name"] == "dataflow" and gate["status"] == "failed" for gate in bad["report"]["gates"])
        path = "/developer/projects/" + self.project_id + "/versions"
        existing = self.get(path)
        assert not any(item["version"] == "0.1.1" for item in existing), "Version 0.1.1 already exists; reconcile lifecycle state before retrying"
        target = DIRECTORY / (self.project_id + "-0.1.1.zip")
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as output:
            for name in source.namelist():
                content = source.read(name)
                if name == "manifest.json":
                    manifest = json.loads(content)
                    manifest["version"] = "0.1.1"
                    content = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
                output.writestr(name, content)
        self.select_project()
        page = self.page
        page.get_by_label("开发分支", exact=True).fill("main")
        page.get_by_label(re.compile(r"^分支基线版本")).select_option(bad["id"])
        page.get_by_label("模块 ZIP 文件", exact=True).set_input_files(str(target))
        expect(page.get_by_role("button", name="上传并启动自动验收", exact=True)).to_be_enabled()
        self.screenshot("good-before-upload")
        self.step = "upload_good_submit"
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1" + path and response.request.method == "POST") as submission:
            page.get_by_role("button", name="上传并启动自动验收", exact=True).click()
        good = self.data(submission.value)
        assert good["version"] == "0.1.1" and good["project_id"] == self.project_id
        # Persist the accepted ID before subsequent browser assertions so a slow
        # UI or lost navigation cannot accidentally cause another upload.
        current = json.loads(self.lifecycle_path.read_text(encoding="utf-8"))
        assert current["project_id"] == self.project_id and not current.get("good_version_id")
        current["good_version_id"] = good["id"]
        current.setdefault("checks", []).append({"check": "browser_upload", "passed": True,
            "version_id": good["id"], "version": good["version"], "package": target.name,
            "method": "real browser file input and submit, backend POST response received"})
        self.lifecycle_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        self.state = current
        persisted = next(item for item in self.get(path) if item["id"] == good["id"])
        assert persisted["base_version_id"] == bad["id"]
        expect(page.locator('section[aria-label="版本验收详情"]')).to_contain_text("0.1.1")
        self.record("corrected_version_uploaded_through_real_ui", version_id=good["id"],
                    status_at_acceptance=good["status"], screenshot=self.screenshot("good-after-upload"))

    def installed_version(self):
        from playwright.sync_api import expect

        self.step = "installed_version_and_release"
        good = self.get("/developer/versions/" + self.state["good_version_id"])
        assert good["status"] == "passed" and good["release_job_id"] and good["version"] == self.expected_version
        job = next(item for item in self.get("/developer/releases") if item["id"] == good["release_job_id"])
        assert job["status"] == "succeeded", job["status"]
        platform = self.get("/developer/platform-status")
        assert platform["environment"]["revision"] == good["candidate_commit"]
        self.installed_module_version = good["version"]
        self.select_project()
        page = self.page
        page.locator(".dev-table tbody tr").filter(has_text=good["version"]).get_by_role("button", name="查看验收", exact=True).click()
        detail = page.locator('section[aria-label="版本验收详情"]')
        expect(detail).to_contain_text("验收通过")
        expect(detail).to_contain_text("发布成功")
        expect(detail).to_contain_text(good["candidate_commit"])
        expect(detail.get_by_role("link", name="进入测试环境模块配置与预览 ↗")).to_have_attribute("href", STAGING + "/developer")
        expect(detail.get_by_role("button", name="重新验收", exact=True)).to_have_count(0)
        screenshot = self.screenshot("accepted-version")
        detail.get_by_role("button", name="查看发布记录", exact=True).click()
        job_card = page.locator("article.job").filter(has_text=good["candidate_commit"]).first
        expect(job_card).to_contain_text("成功")
        self.record("accepted_version_matches_real_successful_release", version_id=good["id"],
                    release_job_id=job["id"], installed_revision=good["candidate_commit"],
                    screenshot=screenshot, release_screenshot=self.screenshot("release"))

    def workflow(self):
        from playwright.sync_api import expect

        self.step = "readonly_workflow_save_and_run"
        assert any(m["manifest"]["id"] == "action_progress" for m in self.get("/developer/modules"))
        page = self.page
        page.get_by_role("button", name="数据编排", exact=True).click()
        page.get_by_role("button", name="新建编排", exact=True).click()
        workflow_id = "browser_flow_" + uuid.uuid4().hex[:10]
        name = "浏览器只读编排验收 " + workflow_id[-10:]
        page.get_by_label("编排编号", exact=True).fill(workflow_id)
        page.get_by_label("编排名称", exact=True).fill(name)
        page.get_by_role("button", name="添加调用节点", exact=True).click()
        page.get_by_label(re.compile(r"^调用模块")).select_option("action_progress")
        page.get_by_label(re.compile(r"^节点操作")).select_option("read")
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/developer/workflows" and response.request.method == "POST") as saved:
            page.get_by_role("button", name="检查并保存编排", exact=True).click()
        workflow = self.data(saved.value)
        assert workflow["id"] == workflow_id and not workflow["published_revision"]
        self.workflow_name = name
        page.get_by_label(re.compile(r"^运行模式")).select_option("fixture")
        with page.expect_response(lambda response: urlsplit(response.url).path == f"/api/v1/developer/workflows/{workflow_id}/run") as executed:
            page.get_by_role("button", name="运行并检查数据流", exact=True).click()
        result = self.data(executed.value)
        assert result["status"] == "succeeded" and not result["action_committed"], result
        assert result["trace"] and all(node["operation"] == "read" for node in result["trace"])
        expect(page.locator('section[aria-label="编排运行结果"]')).to_contain_text("没有提交业务操作")
        screenshot = self.screenshot("workflow-result")
        page.reload()
        page.locator('aside[aria-label="工作流列表"]').get_by_role("button").filter(has_text=name).click()
        expect(page.get_by_label("编排编号", exact=True)).to_have_value(workflow_id)
        expect(page.get_by_text(result["id"], exact=True)).to_be_visible()
        page.get_by_role("button", name="查看运行链路", exact=True).click()
        expect(page.locator('section[aria-label="编排运行结果"]')).to_contain_text("成功")
        persisted = next(item for item in self.get("/developer/workflows") if item["id"] == workflow_id)
        runs = self.get(f"/developer/workflows/{workflow_id}/runs")
        assert persisted["definition"] == workflow["definition"]
        assert any(item["id"] == result["id"] and item["status"] == "succeeded" for item in runs)
        self.record("readonly_workflow_saved_run_and_persisted_after_refresh", workflow_id=workflow_id,
                    run_id=result["id"], published=False, action_committed=False, screenshot=screenshot,
                    refresh_screenshot=self.screenshot("workflow-after-refresh"))

    def preview_input_validation(self):
        from playwright.sync_api import expect

        self.step = "skill_preview_input_contract"
        page = self.page
        page.get_by_role("button", name="调试预览", exact=True).click()
        page.get_by_label("模块", exact=True).select_option("plan_progress_skill")
        page.get_by_label("数据模式", exact=True).select_option("fixture")
        page.get_by_label("场景", exact=True).select_option("normal")
        expect(page.get_by_label("技能返回 JSON", exact=True)).to_be_visible()
        endpoint = "/api/v1/developer/modules/plan_progress_skill/preview"
        page.get_by_label("模块输入 JSON", exact=True).fill('{"expected_total":999}')
        with page.expect_response(lambda response: urlsplit(response.url).path == endpoint) as rejected:
            page.get_by_role("button", name="运行此输入", exact=True).click()
        response = rejected.value
        body = response.json()
        assert body.get("code") and "expected_total" in body.get("message", ""), body
        expected_error = {"path": endpoint, "http_status": response.status, "code": body["code"],
                          "message": self.redact(body["message"])}
        self.expected_api_errors.setdefault("workbench", []).append(expected_error)
        expect(page.locator(".module-error")).to_contain_text("expected_total")
        error_shot = self.screenshot("skill-input-rejected")
        page.get_by_label("模块输入 JSON", exact=True).fill('{"expected_total":2}')
        with page.expect_response(lambda result: urlsplit(result.url).path == endpoint) as accepted:
            page.get_by_role("button", name="运行此输入", exact=True).click()
        result = self.data(accepted.value)
        assert result["data"]["total"] == 2
        assert accepted.value.request.post_data_json["expected_version"] == result["module_version"]
        expect(page.locator(".module-error")).to_have_count(0)
        expect(page.get_by_label("技能返回 JSON", exact=True)).to_contain_text('"total": 2')
        self.record("skill_preview_rejects_inconsistent_input_and_accepts_corrected_input",
                    module_version=result["module_version"], expected_total=2,
                    rejection_screenshot=error_shot, success_screenshot=self.screenshot("skill-input-accepted"))

    def narrow(self, environment):
        from playwright.sync_api import expect

        self.step = environment + "_narrow_screen"
        page = self.page
        page.set_viewport_size({"width": 390, "height": 844})
        tabs = ("开始开发", "项目与版本", "数据编排") if environment == "workbench" else ("模块列表", "调试预览")
        screenshots = []
        for index, label in enumerate(tabs):
            page.get_by_role("button", name=label, exact=True).click()
            expect(page.get_by_role("button", name=label, exact=True)).to_have_class("active")
            if label == "开始开发":
                expect(page.get_by_role("heading", name="生成你的模块模板", exact=True)).to_be_visible()
            elif label == "项目与版本":
                self.select_project()
                if self.installed_module_version:
                    page.locator(".dev-table tbody tr").filter(has_text=self.installed_module_version).get_by_role("button", name="查看验收", exact=True).click()
                    expect(page.locator('section[aria-label="版本验收详情"]')).to_contain_text("发布成功")
            elif label == "数据编排":
                expect(page.get_by_label("编排名称", exact=True)).to_be_visible()
                if self.workflow_name:
                    page.locator('aside[aria-label="工作流列表"]').get_by_role("button").filter(has_text=self.workflow_name).click()
                    page.get_by_role("button", name="查看运行链路", exact=True).click()
                    expect(page.locator('section[aria-label="编排运行结果"]')).to_contain_text("成功")
            elif label == "模块列表":
                expect(page.locator("article.dev-card").filter(has_text=self.project_id)).to_be_visible()
            elif label == "调试预览":
                expect(page.locator(".module-host").get_by_role("progressbar")).to_be_visible()
            page.wait_for_timeout(250)
            width = page.evaluate("({content:document.documentElement.scrollWidth, viewport:window.innerWidth})")
            screenshots.append(self.screenshot(environment + "-narrow-" + str(index + 1)))
            assert width["content"] <= width["viewport"] + 1, {"tab": label, **width}
        self.record(environment + "_narrow_screen_without_page_overflow", width=390, screenshots=screenshots)
        page.set_viewport_size({"width": 1440, "height": 1000})

    def staging_module(self):
        from playwright.sync_api import expect

        self.step = "installed_module_management_preview_and_home"
        page = self.page
        module = next(m for m in self.get("/developer/modules") if m["manifest"]["id"] == self.project_id)
        assert module["manifest"]["version"] == self.expected_version and module["effective_enabled"], "Run API verify phase to authorize the expected installed module first"
        card = page.locator("article.dev-card").filter(has_text=self.project_id)
        expect(card.get_by_role("checkbox", name="启用模块", exact=True)).to_be_checked()
        expect(card.get_by_role("checkbox", name="启用模块", exact=True)).to_be_enabled()
        expect(card.get_by_role("button", name="保存配置", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="项目与版本", exact=True)).to_have_count(0)
        expect(page.get_by_role("link", name="前往开发工作台上传与发布 ↗")).to_have_attribute("href", WORKBENCH + "/developer")
        management_shot = self.screenshot("staging-modules")
        card.get_by_role("button", name="预览模块", exact=True).click()
        expect(page.get_by_label("模块", exact=True)).to_have_value(self.project_id)
        page.get_by_role("button", name="查看详情 →", exact=True).click()
        dialog = page.get_by_role("dialog", name=module["manifest"]["name"], exact=True)
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role("checkbox").first).to_be_disabled()
        preview_shot = self.screenshot("staging-preview-detail")
        dialog.get_by_role("button", name="关闭", exact=True).click()
        with page.expect_response(lambda response: urlsplit(response.url).path == f"/api/v1/developer/modules/{self.project_id}/preview") as live_response:
            page.get_by_label("数据模式", exact=True).select_option("live")
        live = self.data(live_response.value)
        assert live_response.value.request.post_data_json["mode"] == "live"
        expect(page.locator(".module-host").get_by_role("progressbar")).to_be_visible()
        expect(page.locator(".module-error")).to_have_count(0)
        self.narrow("staging")
        # Span a complete polling interval before checking that the staging UI
        # never asks for workbench-only project/queue information.
        page.wait_for_timeout(5200)
        forbidden = {"/api/v1/developer/platform-status", "/api/v1/developer/projects", "/api/v1/developer/releases"}
        assert not forbidden.intersection(self.requests["staging"]), self.requests["staging"]
        page.goto(STAGING + "/")
        home_card = page.locator(f'.module-host[data-block="{self.project_id}"]')
        expect(home_card).to_be_visible()
        expect(home_card.get_by_role("progressbar")).to_be_visible()
        expect(home_card.locator(".module-error")).to_have_count(0)
        page.reload()
        expect(home_card.get_by_role("progressbar")).to_be_visible()
        self.record("installed_module_admin_controls_preview_detail_live_data_and_home", version=self.expected_version,
                    management_screenshot=management_shot, preview_screenshot=preview_shot,
                    home_screenshot=self.screenshot("staging-home"),
                    policies_changed=False, workbench_only_requests=0, live_result=live)

    def watch_update(self, browser):
        from playwright.sync_api import expect

        self.login(browser, "staging")
        self.step = "watch_update_baseline"
        page = self.page
        baseline_deadline = time.monotonic() + 10
        while not self.version_reads["staging"] and time.monotonic() < baseline_deadline:
            page.wait_for_timeout(200)
        assert self.version_reads["staging"], "The deployed frontend did not read version.json"
        initial_revision = self.version_reads["staging"][-1]
        context = self.get("/developer/context")
        assert context["revision"] == initial_revision
        page.get_by_role("button", name="数据编排", exact=True).click()
        page.get_by_role("button", name="新建编排", exact=True).click()
        marker = "未保存输入必须保留 " + uuid.uuid4().hex[:10]
        page.get_by_label("编排名称", exact=True).fill(marker)
        initial_url, initial_origin = page.url, page.evaluate("performance.timeOrigin")
        assert all(item["name"] != marker for item in self.get("/developer/workflows"))
        self.record("update_watch_ready_with_unsaved_input", initial_revision=initial_revision,
                    initial_url=initial_url, screenshot=self.screenshot("update-waiting"))
        self.step = "watch_update_waiting_for_real_revision"
        deadline = time.monotonic() + self.args.update_timeout
        logged = time.monotonic()
        notice = page.locator('.version-notice[aria-label="新版本提示"]')
        while not notice.is_visible():
            if time.monotonic() >= deadline:
                raise TimeoutError("No real frontend update notice before update timeout")
            page.wait_for_timeout(1000)
            if time.monotonic() - logged >= 30:
                print("WAIT real frontend revision change; unsaved draft remains open", flush=True)
                logged = time.monotonic()
        self.step = "watch_update_preserves_input"
        expect(page.get_by_label("编排名称", exact=True)).to_have_value(marker)
        assert page.url == initial_url and page.evaluate("performance.timeOrigin") == initial_origin
        assert all(item["name"] != marker for item in self.get("/developer/workflows"))
        updated_revision = self.version_reads["staging"][-1]
        assert updated_revision != initial_revision
        notice_shot = self.screenshot("update-notice-preserves-input")
        with page.context.expect_page() as opened:
            notice.get_by_role("link", name="在新标签页更新 ↗", exact=True).click()
        fresh = opened.value
        self.observe(fresh, "staging-updated-tab")
        fresh.wait_for_load_state("domcontentloaded")
        self.page = fresh
        expect(fresh.get_by_role("heading", name="测试环境模块管理", exact=True)).to_be_visible()
        fresh.get_by_role("button", name="模块列表", exact=True).click()
        new_context = self.get("/developer/context")
        actual_version = fresh.request.get(STAGING + "/version.json").json()["revision"]
        assert new_context["revision"] == actual_version == updated_revision
        module = next(item for item in self.get("/developer/modules") if item["manifest"]["id"] == self.project_id)
        assert module["manifest"]["version"] == self.expected_version
        expect(fresh.locator("article.dev-card").filter(has_text=self.project_id)).to_be_visible()
        expect(page.get_by_label("编排名称", exact=True)).to_have_value(marker)
        assert page.url == initial_url and page.evaluate("performance.timeOrigin") == initial_origin
        self.record("real_revision_notice_new_tab_and_unsaved_input_preserved", initial_revision=initial_revision,
                    updated_revision=updated_revision, unsaved_workflow_not_persisted=True,
                    old_page_not_reloaded=True, installed_module=self.project_id,
                    notice_screenshot=notice_shot, updated_tab_screenshot=self.screenshot("update-new-tab"))

    def run(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=self.args.channel, headless=True)
            try:
                if self.args.watch_update:
                    self.watch_update(browser)
                else:
                    workbench = self.login(browser, "workbench")
                    if not self.args.installed_only:
                        package = self.download_template()
                        self.forms(package)
                    if self.args.upload_good:
                        self.upload_good(package)
                    else:
                        self.installed_version()
                        if not self.args.installed_only:
                            self.workflow()
                            self.preview_input_validation()
                            self.narrow("workbench")
                        workbench.close()
                        self.login(browser, "staging")
                        self.staging_module()
                self.step = "browser_errors"
                assert not any(self.errors.values()), self.errors
                developer_errors = {environment: [error for error in errors if error["path"].startswith("/api/v1/developer/")]
                                    for environment, errors in self.api_errors.items()}
                for environment, expected in self.expected_api_errors.items():
                    for error in expected:
                        assert error in developer_errors[environment], "Expected API rejection was not observed"
                        developer_errors[environment].remove(error)
                assert not any(developer_errors.values()), developer_errors
                self.report.update(passed=True, api_errors=self.api_errors, page_errors=self.errors,
                                   expected_api_rejections=self.expected_api_errors,
                                   finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
                self.save()
            except Exception as exc:  # noqa: BLE001 - Persist sanitized evidence for every failed browser step.
                self.report.update(failed_step=self.step, error=self.redact(exc),
                                   api_errors=self.api_errors, page_errors=self.errors)
                if self.page and not self.page.is_closed():
                    self.report["failure_screenshot"] = self.screenshot("failure")
                self.save()
                raise RuntimeError(self.redact(exc)) from None
            finally:
                browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--upload-good", action="store_true", help="Submit corrected 0.1.1 via UI after bad version failed; updates lifecycle state")
    modes.add_argument("--watch-update", action="store_true", help="Wait for a real staging deployment update while preserving unsaved input")
    modes.add_argument("--installed-only", action="store_true", help="Verify the lifecycle expected_version in release UI, staging preview and home; no extra workflow")
    parser.add_argument("--update-timeout", type=int, default=2400, help="Maximum seconds to wait for the real frontend update notice")
    parser.add_argument("--lifecycle", type=Path, default=LIFECYCLE)
    parser.add_argument("--channel", default="msedge", help="Installed Chromium-family Playwright channel")
    BrowserAcceptance(parser.parse_args()).run()
