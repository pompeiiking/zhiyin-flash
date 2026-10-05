"""Real isolated-environment acceptance. Never connects to the current 5173 database.

Install Playwright in the local development venv; uses installed Microsoft Edge.
Evidence is written under .platform/acceptance, without credentials or tokens.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import uuid

from module_executor import request, read_env

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8014"
WEB = "http://127.0.0.1:5174"
PREFIX = "/api/v1"


def main(browser=True, restart=True):
    evidence = ROOT / ".platform" / "acceptance"
    evidence.mkdir(parents=True, exist_ok=True)
    env = read_env(ROOT / ".platform" / "workbench.env")
    tokens = {}
    results = []

    def record(name, **values):
        results.append({"check": name, "passed": True, **values})
        (evidence / "integration.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS", name, flush=True)

    def api(path, actor="admin", body=None, method=None):
        return request(BASE, PREFIX + path, token=tokens[actor], body=body, method=method)

    def denied(path, actor="module_student", body=None, method=None):
        try:
            api(path, actor, body, method)
        except (urllib.error.HTTPError, RuntimeError):
            return
        raise AssertionError("Request should have been denied: " + path)

    for account, role in (("admin", "admin"), ("module_developer", "developer"), ("module_student", "student")):
        login = request(BASE, PREFIX + "/app/auth/login", body={"account": account, "password": env["PLATFORM_ACCOUNT_PASSWORD"]})
        assert login["role"] == role
        tokens[account] = login["token"]
    denied("/developer/modules")
    denied("/developer/checks", body={})
    denied("/developer/releases")
    api("/developer/context", "module_developer")
    record("database_roles_and_management_access")

    module = next(m for m in api("/developer/modules") if m["manifest"]["id"] == "action_progress")
    original = module["policy"]
    policy = original.copy()
    policy["enabled"] = True
    policy["reads"] = ["plan.read"]
    policy["actions"] = ["plan.task.set_done"]
    policy["agents"] = ["path_planner"]
    policy = api("/developer/modules/action_progress/policy", body=policy, method="PUT")
    denied("/developer/modules/action_progress/policy", "module_developer", policy, "PUT")
    denied("/developer/modules/action_progress/policy", "admin", original, "PUT")
    record("administrator_grants_and_optimistic_concurrency")

    before = api("/app/modules/action_progress/data", "module_developer")
    for fixture in ("normal", "empty"):
        result = api("/developer/modules/action_progress/preview", "module_developer", {"mode": "fixture", "fixture": fixture})
        assert result["empty"] == (fixture == "empty")
    denied("/developer/modules/action_progress/preview", "module_developer", {"mode": "fixture", "fixture": "error"})
    assert api("/app/modules/action_progress/data", "module_developer") == before
    record("fixtures_normal_empty_error_without_business_writes")

    other_before = api("/app/modules/action_progress/data", "module_student")
    task = before["data"]["tasks"][-1]
    body = {"action": "plan.task.set_done", "payload": {"task_id": task["task_id"], "done": not task["done"]}}
    after = api("/app/modules/action_progress/actions", "module_developer", body)
    plan = api("/app/plan/action", "module_developer")
    assert next(t for p in plan["phases"] for t in p["tasks"] if t["task_id"] == task["task_id"])["done"] == (not task["done"])
    assert api("/app/modules/action_progress/data", "module_student") == other_before
    denied("/app/modules/action_progress/actions", "module_developer", {**body, "payload": {**body["payload"], "user_id": "module_student"}})
    record("task_action_existing_business_consistency_and_user_isolation", completed=after["data"]["completed"])

    policy = api("/developer/modules/action_progress/policy", body={**policy, "actions": []}, method="PUT")
    denied("/app/modules/action_progress/actions", "module_developer", body)
    policy = api("/developer/modules/action_progress/policy", body={**policy, "enabled": False}, method="PUT")
    assert all(m["manifest"]["id"] != "action_progress" for m in api("/app/modules"))
    denied("/app/modules/action_progress/data", "module_developer")
    api("/app/modules/achievements/data", "module_developer")
    policy = api("/developer/modules/action_progress/policy", body={**policy, "enabled": True, "actions": ["plan.task.set_done"]}, method="PUT")
    record("revocation_disable_and_other_module_availability")
    report = api("/developer/checks", "module_developer", {})
    assert report["passed"], report

    # Revoke a developer in the actual DB, then reuse their existing JWT.
    command = ["docker", "exec", "zhiyin-module-workbench-api-1", "python", "scripts/module_admin.py", "module_developer", "--role"]
    subprocess.run([*command, "student"], check=True, capture_output=True)
    try:
        denied("/developer/context", "module_developer")
    finally:
        subprocess.run([*command, "developer"], check=True, capture_output=True)
    api("/developer/context", "module_developer")
    record("existing_token_obeys_current_database_role")

    # Public registration cannot select an administrative role.
    temporary = "accept_" + uuid.uuid4().hex[:10]
    public = request(BASE, PREFIX + "/app/auth/register", body={"account": temporary, "password": env["PLATFORM_ACCOUNT_PASSWORD"]})
    assert public["role"] == "student"
    record("public_registration_is_student")

    if restart:
        subprocess.run(["docker", "restart", "zhiyin-module-workbench-api-1", "zhiyin-module-workbench-postgres-1", "zhiyin-module-workbench-redis-1"], check=True, capture_output=True)
        for attempt in range(60):
            try:
                persisted = api("/app/modules/action_progress/data", "module_developer")
                break
            except Exception:
                if attempt == 59:
                    raise
                time.sleep(2)
        assert persisted == after
        assert any(r["id"] == report["id"] for r in api("/developer/checks"))
        assert next(m for m in api("/developer/modules") if m["manifest"]["id"] == "action_progress")["policy"] == policy
        record("postgres_redis_api_restart_preserves_data_grants_and_checks")

    if browser:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser_instance = p.chromium.launch(channel="msedge", headless=True)
            context = browser_instance.new_context(viewport={"width": 1440, "height": 1000})
            context.add_init_script("localStorage.setItem('zhiyin_token', " + json.dumps(tokens["admin"]) + ")")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(WEB + "/developer")
            page.get_by_role("heading", name="模块开发工作台").wait_for()
            page.get_by_role("button", name="模块列表", exact=True).click()
            page.get_by_role("button", name="预览模块").first.wait_for()
            page.screenshot(path=str(evidence / "developer-desktop.png"), full_page=True)
            page.get_by_role("button", name="调试预览", exact=True).click()
            page.get_by_label("模块", exact=True).select_option("action_progress")
            page.get_by_role("button", name="查看详情 →").click()
            dialog = page.get_by_role("dialog")
            dialog.wait_for()
            assert dialog.get_by_role("checkbox").first.is_disabled()
            page.screenshot(path=str(evidence / "preview-detail.png"), full_page=True)
            dialog.get_by_role("button", name="关闭", exact=True).click()
            page.get_by_label("场景", exact=True).select_option("empty")
            page.get_by_text("还没有行动计划", exact=False).wait_for()
            page.get_by_label("场景", exact=True).select_option("error")
            page.locator(".module-error").wait_for()
            page.screenshot(path=str(evidence / "preview-error.png"), full_page=True)
            original_admin = api("/app/modules/action_progress/data")
            page.get_by_label("数据模式", exact=True).select_option("live")
            page.get_by_role("button", name="查看详情 →").click()
            checkbox = page.get_by_role("dialog").get_by_role("checkbox").last
            admin_done = checkbox.is_checked()
            checkbox.set_checked(not admin_done)
            expected = original_admin["data"]["completed"] + (-1 if admin_done else 1)
            for _ in range(30):
                if api("/app/modules/action_progress/data")["data"]["completed"] == expected:
                    break
                time.sleep(.2)
            else:
                raise AssertionError("Browser action did not reach the existing business service")
            assert sum(t["done"] for phase in api("/app/plan/action")["phases"] for t in phase["tasks"]) == expected
            page.get_by_role("dialog").get_by_role("button", name="关闭", exact=True).click()
            page.reload()
            assert api("/app/modules/action_progress/data")["data"]["completed"] == expected
            api("/app/modules/action_progress/actions", body={"action": "plan.task.set_done", "payload": {
                "task_id": original_admin["data"]["tasks"][-1]["task_id"], "done": admin_done}})
            record("browser_real_action_original_plan_and_refresh_consistency")
            page.set_viewport_size({"width": 390, "height": 844})
            page.get_by_role("button", name="模块列表", exact=True).click()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.screenshot(path=str(evidence / "developer-mobile.png"), full_page=True)
            page.reload()
            page.get_by_role("button", name="预览模块").first.wait_for()
            page.goto(WEB + "/")
            page.locator(".module-host").first.wait_for()
            page.screenshot(path=str(evidence / "home-mobile.png"), full_page=True)
            assert not errors, errors
            browser_instance.close()
        record("browser_shared_components_detail_empty_error_narrow_screen_refresh_home")
    # Restore the test task and original grant choices, using the current revision.
    api("/app/modules/action_progress/actions", "module_developer", {**body, "payload": {**body["payload"], "done": task["done"]}})
    api("/developer/modules/action_progress/policy", body={**original, "revision": policy["revision"]}, method="PUT")
    record("restored_original_task_and_policy")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()
    main(not args.no_browser, not args.no_restart)
