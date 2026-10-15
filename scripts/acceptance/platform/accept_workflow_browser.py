"""Real workbench UI acceptance for workflow publish/pause/resume.

No API interception. All workflow configuration changes use visible controls.
The ordinary-user SDK endpoint is called with that user's real browser session.
Only a synthetic read-only workflow is saved; existing plans remain unchanged.
"""
from __future__ import annotations

import argparse
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from accept_developer_browser import DIRECTORY, LIFECYCLE, WORKBENCH, BrowserAcceptance


class WorkflowReleaseAcceptance(BrowserAcceptance):
    def __init__(self, args):
        super().__init__(args)
        self.output = DIRECTORY / "developer-v2-workflow-release.json"
        self.report = {
            "method": "real browser UI and real authenticated public SDK; no API interception",
            "mode": "workflow-publish-pause-resume",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "scope": {"environment": WORKBENCH, "creates_synthetic_workflow": True,
                      "changes_existing_plans": False, "uploads_version": False},
            "checks": [], "passed": False,
        }
        self.flow_id = "browser_pause_" + uuid.uuid4().hex[:10]
        self.report["workflow_id"] = self.flow_id

    def screenshot(self, name):
        target = DIRECTORY / ("developer-v2-workflow-release-" + name + ".png")
        self.page.screenshot(path=str(target), full_page=True)
        return target.name

    def click_api(self, button, endpoint, stage):
        self.step = stage
        self.page.evaluate("stage => { window.__workflowOperation = stage }", stage)
        with self.page.expect_response(lambda response: urlsplit(response.url).path == endpoint
                                       and response.request.method == "POST") as event:
            button.click()
        result = self.data(event.value)
        # The API result and list refresh both finish before the busy flag clears.
        from playwright.sync_api import expect
        expect(self.page.get_by_role("button", name="检查并保存编排", exact=True)).to_be_enabled()
        return result

    def observe_busy(self):
        self.page.evaluate("""() => {
          window.__workflowBusyEvidence = [];
          window.__workflowOperation = 'idle';
          const names = ['检查并保存编排', '发布当前修订', '暂停发布'];
          new MutationObserver(() => {
            const controls = [...document.querySelectorAll('button')]
              .filter(button => names.includes(button.textContent.trim()))
              .map(button => ({ label: button.textContent.trim(), disabled: button.disabled }));
            if (controls.length && controls.every(button => button.disabled)) {
              window.__workflowBusyEvidence.push({ operation: window.__workflowOperation, controls });
            }
          }).observe(document.querySelector('.developer'), {
            subtree: true, attributes: true, attributeFilter: ['disabled']
          });
        }""")

    def public_request(self, page, path, body=None):
        return page.evaluate("""async ({path, body}) => {
          const response = await fetch('/api/v1' + path, {
            method: body === null ? 'GET' : 'POST',
            headers: { Authorization: 'Bearer ' + localStorage.getItem('zhiyin_token'),
                       'Content-Type': 'application/json' },
            ...(body === null ? {} : {body: JSON.stringify(body)})
          });
          return {http_status: response.status, body: await response.json()};
        }""", {"path": path, "body": body})

    @staticmethod
    def public_data(response):
        assert response["http_status"] < 400 and response["body"]["code"] == 0, response
        return response["body"]["data"]

    def ordinary_login(self, browser):
        from playwright.sync_api import expect

        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        self.observe(page, "ordinary-user")
        page.goto(WORKBENCH + "/developer")
        page.locator('input[name="account"]').fill("module_student")
        page.locator('input[name="password"]').fill(self.workbench_env["PLATFORM_ACCOUNT_PASSWORD"])
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/app/auth/login") as event:
            page.get_by_role("button", name="登录并进入", exact=True).click()
        value = self.data(event.value)
        self.secrets.add(value["token"])
        assert value["role"] == "student", value["role"]
        page.wait_for_url(WORKBENCH + "/")
        expect(page.locator("body")).to_be_visible()
        self.record("ordinary_user_real_ui_login", account="module_student", role=value["role"])
        return page

    def scenario(self, browser):
        from playwright.sync_api import expect

        self.login(browser, "workbench")
        page = self.page
        before_plan = self.get("/app/plan/action")
        module = next(item for item in self.get("/developer/modules")
                      if item["manifest"]["id"] == "action_progress")
        assert module["effective_enabled"] and "plan.read" in module["policy"]["reads"]
        installed_version = module["manifest"]["version"]
        page.get_by_role("button", name="数据编排", exact=True).click()
        page.get_by_role("button", name="新建编排", exact=True).click()
        name = "发布暂停只读验收 " + self.flow_id[-10:]
        page.get_by_label("编排编号", exact=True).fill(self.flow_id)
        page.get_by_label("编排名称", exact=True).fill(name)
        page.get_by_role("button", name="添加调用节点", exact=True).click()
        node = page.locator(".workflow-node")
        node.get_by_label(re.compile(r"^调用模块")).select_option("action_progress")

        self.step = "current_version_button_preserves_node_configuration"
        node.get_by_label("锁定模块版本", exact=True).fill("0.0.0")
        node.get_by_label(re.compile(r"^节点操作")).select_option("action")
        node.get_by_label(re.compile(r"^业务操作")).select_option("plan.task.set_done")
        node.get_by_label("固定输入 JSON", exact=True).fill('{"done":false}')
        node.get_by_role("button", name="添加输入映射", exact=True).click()
        node.get_by_label("目标输入字段", exact=True).fill("task_id")
        node.get_by_label("来源路径", exact=True).fill("$input/task_id")
        expect(node).to_contain_text("当前安装版本：" + installed_version)
        node.get_by_role("button", name="使用当前安装版本", exact=True).click()
        expect(node.get_by_label("锁定模块版本", exact=True)).to_have_value(installed_version)
        expect(node.get_by_label(re.compile(r"^节点操作"))).to_have_value("action")
        expect(node.get_by_label(re.compile(r"^业务操作"))).to_have_value("plan.task.set_done")
        expect(node.get_by_label("固定输入 JSON", exact=True)).to_have_value('{"done":false}')
        expect(node.get_by_label("目标输入字段", exact=True)).to_have_value("task_id")
        expect(node.get_by_label("来源路径", exact=True)).to_have_value("$input/task_id")
        self.record("current_version_button_keeps_input_bindings_and_action", module_version=installed_version,
                    action_draft_never_saved_or_executed=True, screenshot=self.screenshot("version-shortcut"))
        # The synthetic workflow that is saved and run contains only one read.
        node.get_by_role("button", name="删除映射", exact=True).click()
        node.get_by_label(re.compile(r"^节点操作")).select_option("read")
        node.get_by_label("固定输入 JSON", exact=True).fill("{}")
        self.observe_busy()
        save_button = page.get_by_role("button", name="检查并保存编排", exact=True)
        publish_button = page.get_by_role("button", name="发布当前修订", exact=True)
        pause_button = page.get_by_role("button", name="暂停发布", exact=True)
        endpoint = "/api/v1/developer/workflows/" + self.flow_id
        first = self.click_api(save_button, "/api/v1/developer/workflows", "save_initial_readonly_draft")
        assert first["published_revision"] is None and first["revision"] == 1
        assert all(item["operation"] == "read" and item.get("action") is None
                   for item in first["definition"]["nodes"])
        page.get_by_label(re.compile(r"^运行模式")).select_option("fixture")
        fixture = self.click_api(page.get_by_role("button", name="运行并检查数据流", exact=True),
                                 endpoint + "/run", "initial_fixture_run")
        assert fixture["status"] == "succeeded" and not fixture["action_committed"]
        first_published = self.click_api(publish_button, endpoint + "/publish", "publish_revision_1")
        assert first_published["published_revision"] == 1
        expect(pause_button).to_be_visible()
        self.record("readonly_draft_fixture_and_first_publication", revision=1, run_id=fixture["id"],
                    screenshot=self.screenshot("first-published"))

        ordinary = self.ordinary_login(browser)
        ordinary_plan = self.public_data(self.public_request(ordinary, "/app/plan/action"))
        public_path = "/app/workflows/" + self.flow_id + "/run"
        original_request = {"input": {}, "mode": "live", "confirm_actions": False,
                            "request_id": uuid.uuid4().hex, "expected_revision": 1}
        receipt = self.public_data(self.public_request(ordinary, public_path, original_request))
        assert receipt["status"] == "succeeded" and not receipt["action_committed"]
        duplicate = self.public_data(self.public_request(ordinary, public_path, original_request))
        assert duplicate == receipt, "Before pause the exact request must reuse the persisted receipt"
        self.record("ordinary_user_live_read_and_idempotent_receipt", run_id=receipt["id"], revision=1)

        page.get_by_label("编排名称", exact=True).fill(name + " · 新草稿")
        second = self.click_api(save_button, "/api/v1/developer/workflows", "save_draft_keeps_public_snapshot")
        assert second["revision"] == 2 and second["published_revision"] == 1
        assert second["definition"] == first["definition"]
        expect(page.get_by_text("普通用户当前使用已发布的修订 1。", exact=False)).to_be_visible()
        another = self.public_data(self.public_request(ordinary, public_path,
                                  {**original_request, "request_id": uuid.uuid4().hex}))
        assert another["revision"] == 1 and another["status"] == "succeeded"
        self.record("saving_draft_preserves_published_snapshot", draft_revision=2, published_revision=1)

        unsaved_name = name + " · 未保存输入"
        page.get_by_label("编排名称", exact=True).fill(unsaved_name)
        expect(publish_button).to_be_disabled()
        paused = self.click_api(pause_button, endpoint + "/unpublish", "pause_published_workflow")
        assert paused["published_revision"] is None and paused["revision"] == 2
        assert paused["definition"] == second["definition"] and paused["name"] == second["name"]
        expect(page.get_by_label("编排名称", exact=True)).to_have_value(unsaved_name)
        expect(pause_button).to_have_count(0)
        expect(page.get_by_text("当前未发布，普通用户暂不能运行。", exact=False)).to_be_visible()
        rejects = []
        for label, request in (("new_call", {**original_request, "request_id": uuid.uuid4().hex,
                                            "expected_revision": 2}),
                               ("old_receipt_replay", original_request)):
            rejected = self.public_request(ordinary, public_path, request)
            assert rejected["http_status"] == 404 and rejected["body"]["code"] != 0, rejected
            assert "尚未发布" in rejected["body"]["message"], rejected
            rejects.append({"kind": label, "http_status": rejected["http_status"],
                            "code": rejected["body"]["code"], "message": rejected["body"]["message"]})
        histories = self.get("/developer/workflows/" + self.flow_id + "/runs")
        assert any(item == fixture for item in histories), "Developer fixture history disappeared"
        self.record("pause_rejects_new_and_old_receipt_calls_preserves_draft_and_history",
                    rejections=rejects, unsaved_input_preserved=True, fixture_run_id=fixture["id"],
                    screenshot=self.screenshot("paused"))

        busy_evidence = page.evaluate("window.__workflowBusyEvidence")
        for operation in ("publish_revision_1", "save_draft_keeps_public_snapshot", "pause_published_workflow"):
            assert any(item["operation"] == operation and len(item["controls"]) >= 2
                       and all(control["disabled"] for control in item["controls"])
                       for item in busy_evidence), {"missing_busy_state": operation, "evidence": busy_evidence}
        self.record("save_publish_pause_real_dom_busy_states_are_mutually_exclusive", evidence=busy_evidence)

        self.step = "paused_state_refresh_and_history"
        page.reload()
        page.get_by_role("button", name="数据编排", exact=True).click()
        page.locator('aside[aria-label="工作流列表"]').get_by_role("button").filter(has_text=name).click()
        expect(page.get_by_label("编排名称", exact=True)).to_have_value(second["name"])
        expect(pause_button).to_have_count(0)
        expect(page.get_by_text(fixture["id"], exact=True)).to_be_visible()
        stored = next(item for item in self.get("/developer/workflows") if item["id"] == self.flow_id)
        assert stored == paused
        self.observe_busy()
        paused_fixture = self.click_api(page.get_by_role("button", name="运行并检查数据流", exact=True),
                                        endpoint + "/run", "paused_owner_fixture_run")
        assert paused_fixture["status"] == "succeeded" and not paused_fixture["action_committed"]
        resumed = self.click_api(publish_button, endpoint + "/publish", "republish_revision_2")
        assert resumed["published_revision"] == 2 and resumed["definition"] == second["definition"]
        restored = self.public_data(self.public_request(ordinary, public_path,
                                   {**original_request, "request_id": uuid.uuid4().hex, "expected_revision": 2}))
        assert restored["status"] == "succeeded" and restored["revision"] == 2
        assert not restored["action_committed"]
        page.reload()
        page.get_by_role("button", name="数据编排", exact=True).click()
        page.locator('aside[aria-label="工作流列表"]').get_by_role("button").filter(has_text=name).click()
        expect(pause_button).to_be_enabled()
        expect(page.get_by_text("普通用户当前使用已发布的修订 2。", exact=False)).to_be_visible()
        expect(page.get_by_text(fixture["id"], exact=True)).to_be_visible()
        expect(page.get_by_text(paused_fixture["id"], exact=True)).to_be_visible()
        assert self.get("/app/plan/action") == before_plan
        assert self.public_data(self.public_request(ordinary, "/app/plan/action")) == ordinary_plan
        self.record("republish_restores_public_run_refresh_and_history_without_business_writes",
                    published_revision=2, run_id=restored["id"], existing_plans_unchanged=True,
                    retained_fixture_run_ids=[fixture["id"], paused_fixture["id"]],
                    screenshot=self.screenshot("republished-refresh"))

        self.step = "browser_errors"
        assert not any(self.errors.values()), self.errors
        assert not self.api_errors["workbench"], self.api_errors["workbench"]
        public_errors = self.api_errors["ordinary-user"]
        assert len(public_errors) == 2 and all(error["http_status"] == 404
                   and error["path"] == "/api/v1" + public_path
                   and "尚未发布" in error["message"] for error in public_errors), public_errors
        self.report.update(passed=True, expected_api_rejections=public_errors,
                           page_errors=self.errors, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        self.save()

    def run(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=self.args.channel, headless=True)
            try:
                self.scenario(browser)
            except Exception as exc:  # noqa: BLE001 - Persist sanitized real browser failure evidence.
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
    parser.add_argument("--lifecycle", type=Path, default=LIFECYCLE)
    parser.add_argument("--channel", default="msedge")
    parser.set_defaults(upload_good=False, installed_only=False, watch_update=False)
    WorkflowReleaseAcceptance(parser.parse_args()).run()
