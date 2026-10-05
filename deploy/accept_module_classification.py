"""Verify application/skill hierarchy in the isolated workbench and its real UI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
from pathlib import Path
from uuid import uuid4

from module_executor import read_env, request

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8014"
WEB = "http://127.0.0.1:5174"
SKILL = "plan_progress_skill"
PARENT = "action_progress"


def main(model=False):
    health = request(BASE, "/healthz")
    assert health["environment"] == "workbench", "Only the isolated workbench may be tested"
    env = read_env(ROOT / ".platform/workbench.env")
    login = request(BASE, "/api/v1/app/auth/login", body={"account": "admin", "password": env["PLATFORM_ACCOUNT_PASSWORD"]})
    evidence = ROOT / ".platform/acceptance"
    evidence.mkdir(parents=True, exist_ok=True)
    results = {}

    def api(path, body=None, method=None, timeout=30):
        return request(BASE, "/api/v1" + path, token=login["token"], body=body, method=method, timeout=timeout)

    def listing():
        return {row["manifest"]["id"]: row for row in api("/developer/modules")}

    def configure(module_id, policy):
        current = listing()[module_id]["policy"]
        return api(f"/developer/modules/{module_id}/policy", {**policy, "revision": current["revision"]}, "PUT")

    modules = listing()
    original = {mid: modules[mid]["policy"] for mid in (PARENT, SKILL)}
    assert modules[PARENT]["manifest"]["kind"] == "hybrid"
    assert modules[SKILL]["manifest"]["kind"] == "tool"
    assert modules[SKILL]["manifest"]["parent_id"] == PARENT
    assert modules[SKILL]["manifest"]["card"] is None
    try:
        configure(PARENT, {**original[PARENT], "enabled": True, "reads": ["plan.read"], "agents": []})
        agents = [a["id"] for a in api("/developer/context")["agents"]]
        configure(SKILL, {**original[SKILL], "enabled": True, "reads": ["plan.read"], "agents": agents})
        assert listing()[SKILL]["effective_enabled"]
        assert SKILL not in {row["manifest"]["id"] for row in api("/app/modules")}
        assert SKILL not in {row["manifest"]["id"] for row in api("/app/modules?surface=conversation")}
        results["classification_and_separate_surfaces"] = True
        value = api(f"/app/modules/{SKILL}/data")
        parent = api(f"/app/modules/{PARENT}/data")
        assert value["data"]["tasks"] == parent["data"]["tasks"]
        assert value["data"]["completed"] == parent["data"]["completed"]
        configure(PARENT, {**original[PARENT], "enabled": False, "agents": []})
        blocked = listing()[SKILL]
        assert blocked["policy"]["enabled"] and not blocked["effective_enabled"]
        assert blocked["blocked_by"] == [PARENT]
        try:
            api(f"/app/modules/{SKILL}/data")
        except urllib.error.HTTPError as exc:
            # AccessDenied uses the existing API's 401/1004 envelope.
            denial = json.loads(exc.read())
            assert exc.code == 401 and denial["code"] == 1004
            assert "模块或所属父模块已停用" in denial["message"]
        else:
            raise AssertionError("Disabled parent did not block skill data access")
        assert not api(f"/developer/modules/{SKILL}/preview", {"mode": "fixture"})["empty"]
        results["parent_disables_live_skill_without_removing_child_policy"] = True

        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1050})
            context.add_init_script("localStorage.setItem('zhiyin_token', " + json.dumps(login["token"]) + ")")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(WEB + "/developer")
            page.get_by_role("button", name="模块列表", exact=True).click()
            page.get_by_label("模块分类", exact=True).select_option("tool")
            page.get_by_text("因所属模块停用而不可用", exact=True).wait_for()
            assert page.locator(".module-grid .dev-card").count() == 1
            page.screenshot(path=str(evidence / "skill-parent-disabled.png"), full_page=True)
            configure(PARENT, {**original[PARENT], "enabled": True, "reads": ["plan.read"], "agents": []})
            page.reload()
            page.get_by_label("模块分类", exact=True).wait_for()
            page.locator(".module-grid .dev-card").filter(has_text=modules[SKILL]["manifest"]["name"]).wait_for()
            page.screenshot(path=str(evidence / "module-hierarchy.png"), full_page=True)
            page.get_by_label("模块分类", exact=True).select_option("tool")
            page.get_by_role("button", name="调试技能", exact=True).click()
            returned = page.get_by_label("技能返回 JSON", exact=True)
            returned.wait_for()
            assert json.loads(returned.inner_text())["data"]["total"] == 2
            page.screenshot(path=str(evidence / "skill-json-preview.png"), full_page=True)
            page.get_by_label("场景", exact=True).select_option("empty")
            page.wait_for_function("document.querySelector('[aria-label=\"技能返回 JSON\"]')?.textContent.includes('\"empty\": true')")
            page.get_by_label("场景", exact=True).select_option("error")
            page.locator(".module-error").wait_for()
            page.get_by_label("数据模式", exact=True).select_option("live")
            returned.wait_for()
            assert json.loads(returned.inner_text())["data"] == value["data"]
            page.goto(WEB + "/")
            page.locator(".module-host").first.wait_for()
            assert page.locator(".module-host").filter(has_text=modules[SKILL]["manifest"]["name"]).count() == 0
            page.goto(WEB + "/developer")
            page.get_by_role("button", name="模块列表", exact=True).click()
            page.get_by_label("模块分类", exact=True).wait_for()
            page.locator(".module-grid .dev-card").filter(has_text=modules[SKILL]["manifest"]["name"]).wait_for()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.screenshot(path=str(evidence / "module-hierarchy-mobile.png"), full_page=True)
            assert not errors, errors
            browser.close()
        results["browser_hierarchy_filter_skill_json_empty_error_live_and_mobile"] = True

        if model:
            # A regression must never overwrite the administrator's own plan.
            # Keep this account and its synthetic conversation as acceptance evidence.
            account = "skill_accept_" + uuid4().hex[:12]
            subprocess.run(["docker", "compose", "--project-directory", str(ROOT),
                "--env-file", str(ROOT / ".platform/workbench.env"), "-p", "zhiyin-module-workbench",
                "-f", str(ROOT / "deploy/compose.platform.yml"), "exec", "-T", "-e", "PLATFORM_ACCOUNT_PASSWORD",
                "api", "python", "scripts/module_admin.py", account, "--role", "student", "--seed"],
                check=True, env={**os.environ, "PLATFORM_ACCOUNT_PASSWORD": env["PLATFORM_ACCOUNT_PASSWORD"]})
            test_login = request(BASE, "/api/v1/app/auth/login", body={"account": account, "password": env["PLATFORM_ACCOUNT_PASSWORD"]})

            def test_api(path, body=None):
                return request(BASE, "/api/v1" + path, token=test_login["token"], body=body, timeout=180)

            results["isolated_model_test_account"] = account
            expected = test_api(f"/app/modules/{SKILL}/data")
            session = test_api("/app/task/enter", {"task_code": "how_to_act"})
            body = {"task_id": session["task_id"], "client_msg_id": "skill_accept_" + uuid4().hex,
                    "message": "请调用计划进度查询技能，读取我的已保存计划，告诉我完成了多少项。不创建或修改计划。"}
            before = test_api("/app/plan/action")
            reply = test_api("/app/conversation/message", body)
            results["real_model_reply"] = reply
            assert before == test_api("/app/plan/action") and not reply["changed_assets"]
            # This exact summary is emitted by the orchestrator only from server-
            # validated module_results. The parent has no agent grant in this test.
            assert any(expected["data"]["summary"] == message["text"] for message in reply["messages"])
            assert not any(renderable["kind"] == f"module.{SKILL}"
                for message in reply["messages"] for renderable in message.get("renderables", []))
            replay = test_api("/app/conversation/message", body)
            assert replay["messages"] == reply["messages"]
            turns = test_api(f"/app/sessions/{session['task_id']}/turns")
            assert expected["data"]["summary"] in json.dumps(turns, ensure_ascii=False)
            results["real_model_skill_without_card_no_business_writes_history_and_retry"] = True
    finally:
        restoration_errors = []
        for module_id in (SKILL, PARENT):
            try:
                restored = configure(module_id, original[module_id])
                assert all(restored[key] == original[module_id][key] for key in ("enabled", "reads", "actions", "agents"))
            except Exception as exc:  # noqa: BLE001 - attempt both restorations and persist every failure
                restoration_errors.append(f"{module_id}: {type(exc).__name__}: {exc}")
        results["original_module_configuration_restored"] = not restoration_errors
        results["restoration_errors"] = restoration_errors
        (evidence / "module-classification.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if restoration_errors:
            raise RuntimeError("Module configuration restoration failed: " + "; ".join(restoration_errors))
    print("PASS application/skill hierarchy, current grants, real data and browser preview")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="store_true")
    main(parser.parse_args().model)
