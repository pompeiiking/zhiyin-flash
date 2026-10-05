"""Mandatory browser checks against one disposable candidate web origin.

The caller starts candidate API/PostgreSQL/Redis on an internal network and adds
only the web service from candidate_web_overlay(). No live environment endpoint
is accepted. The host's trusted browser_python runs this fixed file; passwords
are inherited environment values, never uploaded commands or CLI arguments.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit


PROTECTED_PORTS = {5173, 5174, 5175, 5176, 5177, 8000, 8014, 8015, 8016, 8017}
FIXTURES = ("normal", "empty", "error")
SIZES = {"desktop": {"width": 1440, "height": 1000}, "narrow": {"width": 390, "height": 844}}
CSP = "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def candidate_web_overlay():
    """Merge with compose.bluegreen.yml; do not expose API, Redis or PostgreSQL."""
    return {"services": {"acceptance_web": {
        "image": "${PLATFORM_ACCEPTANCE_WEB_IMAGE:?Set accepted web image}", "profiles": ["acceptance"],
        "environment": {"PLATFORM_SLOT_API": "acceptance_api"},
        "ports": ["127.0.0.1:${PLATFORM_ACCEPTANCE_WEB_PORT:?Set private browser port}:80"],
        "volumes": ["${PLATFORM_BROWSER_NGINX_TEMPLATE:?Set candidate template}:/etc/nginx/templates/default.conf.template:ro"],
        "depends_on": {"acceptance_api": {"condition": "service_healthy"}},
        "networks": ["acceptance", "browser_access"],
    }}, "networks": {"browser_access": {}}}


def candidate_nginx_template():
    # These policy headers are a browser access boundary, not a claim that trusted
    # uploaded backend code runs in a hostile-code sandbox.
    return """server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;
  add_header Content-Security-Policy \"""" + CSP + """\" always;
  location /api/ {
    proxy_pass http://${PLATFORM_SLOT_API}:8000;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_read_timeout 30s;
  }
  location = /healthz { proxy_pass http://${PLATFORM_SLOT_API}:8000; }
  location = /version.json { expires -1; }
  location / { try_files $uri $uri/ /index.html; }
}
"""


def candidate_origin(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid candidate origin") from exc
    require(parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and port is not None
            and 1024 <= port <= 65535 and port not in PROTECTED_PORTS and parsed.username is None
            and parsed.password is None and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment,
            "Browser gate requires an unreserved 127.0.0.1 candidate web port")
    return f"http://127.0.0.1:{port}"


def allocate_web_port(excluded=()):
    for _ in range(100):
        with socket.socket() as handle:
            handle.bind(("127.0.0.1", 0))
            port = handle.getsockname()[1]
        if port not in PROTECTED_PORTS and port not in excluded and port >= 1024:
            return port
    raise RuntimeError("Could not allocate a private candidate browser port")


def dataflow_contract(value, revision):
    require(re.fullmatch(r"[a-f0-9]{40}", revision), "A complete candidate revision is required")
    require(value.get("passed") is True and value.get("configuration_restored") is True,
            "Browser gate requires a passed dataflow report with restored candidate policies")
    require(value.get("revision") == revision, "Dataflow report must identify the same candidate revision")
    require(re.fullmatch(r"df_[a-f0-9]{12}_one", value.get("preview_user_id", "")), "Dataflow report must identify its synthetic preview user")
    modules = value.get("modules")
    require(isinstance(modules, dict) and modules, "Dataflow report has no module coverage")
    for module_id, item in modules.items():
        require(re.fullmatch(r"[a-z][a-z0-9_]{1,47}", module_id), "Invalid reported module ID")
        require(item.get("passed") is True and item.get("kind") in {"application", "tool", "hybrid"},
                f"{module_id}: dataflow acceptance is incomplete")
        require(isinstance(item.get("inputs"), dict) and all(isinstance(item["inputs"].get(fixture), dict) for fixture in FIXTURES),
                f"{module_id}: dataflow report must provide explicit normal/empty/error inputs")
        for fixture in ("normal", "empty"):
            result = item.get("fixtures", {}).get(fixture)
            require(isinstance(result, dict) and isinstance(result.get("data"), dict) and result.get("module_version") == item.get("version"),
                    f"{module_id}.{fixture}: missing verified fixture result/version")
    return modules


def match_module_coverage(reported, installed, revision):
    modules = {item["manifest"]["id"]: item for item in installed}
    require(len(modules) == len(installed) and set(modules) == set(reported),
            "Browser must cover every installed module, including disabled modules and tools")
    for module_id, module in modules.items():
        manifest = module["manifest"]
        require(module.get("source_revision") == revision and manifest.get("version") == reported[module_id]["version"]
                and manifest.get("kind") == reported[module_id]["kind"], f"{module_id}: browser/backend/dataflow version mismatch")
    return modules


def validate_browser_result(value, dataflow, revision):
    require(value.get("gate") == "browser" and value.get("rules_version") == "1" and value.get("passed") is True
            and value.get("no_api_mocking") is True and value.get("revision") == revision,
            "Browser result is missing its successful fixed-gate identity")
    require(value.get("errors") == [] and value.get("network_failures") == [], "Browser reported runtime/network errors")
    modules = value.get("modules", {})
    require(set(modules) == set(dataflow["modules"]), "Browser did not check every candidate module")
    expected_checks = {(fixture, viewport) for fixture in FIXTURES for viewport in SIZES}
    for module_id, item in modules.items():
        expected = dataflow["modules"][module_id]
        checks = item.get("checks", [])
        require(item.get("passed") is True and item.get("version") == expected["version"] and item.get("kind") == expected["kind"]
                and len(checks) == len(expected_checks) and all(check.get("passed") is True for check in checks)
                and {(check.get("fixture"), check.get("viewport")) for check in checks} == expected_checks,
                f"{module_id}: browser fixture/viewport coverage is incomplete")


def atomic_report(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


SURFACE = """({selector}) => {
  const root = document.querySelector(selector);
  if (!root) return {count:0, text:''};
  const nodes = [...root.childNodes].filter(node => {
    if (node.nodeType === Node.TEXT_NODE) return !!node.textContent.trim();
    if (!(node instanceof Element)) return false;
    const visible = element => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.opacity !== '0';
    };
    const media = 'img,svg,canvas,video,audio,progress,meter,input,select,textarea,button,[role=progressbar],[role=checkbox],[role=button]';
    const content = element => {
      if (getComputedStyle(element).display === 'contents') return [...element.children].some(content);
      if (!visible(element)) return false;
      return !!(element.innerText || '').trim() || element.matches(media) || [...element.querySelectorAll(media)].some(visible);
    };
    return content(node);
  });
  return {count:nodes.length, text:nodes.map(node => (node.innerText || node.textContent || '').trim()).join(' ').slice(0,800)};
}"""


class BrowserGate:
    def __init__(self, url, revision, dataflow, output, timeout):
        self.url = candidate_origin(url)
        self.revision = revision
        self.expected = dataflow_contract(dataflow, revision)
        require(30 <= timeout <= 1200, "Browser timeout must be between 30 and 1200 seconds")
        self.deadline = time.monotonic() + timeout
        self.output = output
        self.screenshots = output.parent / (output.stem + "-screenshots")
        self.screenshots.mkdir(parents=True, exist_ok=True)
        self.account = os.environ.get("PLATFORM_BROWSER_ACCOUNT", "")
        self.password = os.environ.get("PLATFORM_BROWSER_PASSWORD", "")
        require(self.account == dataflow["preview_user_id"] and len(self.password) >= 12,
                "Browser must reuse the dataflow synthetic preview identity with a private password")
        self.secrets = [self.password]
        self.page, self.context = None, None
        self.current_module = None
        self.report = {"gate": "browser", "rules_version": "1", "passed": False, "revision": revision,
            "scope": "real_candidate_ui_fixture_rendering", "origin": self.url, "started_at": time.time(),
            "no_api_mocking": True, "modules": {}, "errors": [], "network_failures": [],
            "screenshots_directory": str(self.screenshots), "excluded": ["real model calls", "business UX judgment", "production data"]}

    def remaining(self, cap=15000):
        left = int((self.deadline - time.monotonic()) * 1000)
        require(left > 0, "Browser gate exceeded its time budget")
        return min(cap, left)

    def redact(self, value):
        text = str(value)
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        return text[:4000]

    def save(self):
        atomic_report(self.output, self.report)

    def screenshot(self, name):
        path = self.screenshots / (name + ".png")
        self.page.screenshot(path=str(path), full_page=True, timeout=min(10000, max(1000, int((self.deadline - time.monotonic()) * 1000))))
        return str(path)

    def health(self):
        responses = {}
        ready_until = min(self.deadline, time.monotonic() + 40)
        for path in ("/healthz", "/version.json"):
            while True:
                try:
                    with urllib.request.urlopen(self.url + path, timeout=5) as response:
                        policy = response.headers.get("Content-Security-Policy", "")
                        require("connect-src 'self'" in policy and "default-src 'self'" in policy, "Candidate web is missing its same-origin browser policy")
                        responses[path] = json.load(response)
                    break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= ready_until:
                        raise
                    time.sleep(.5)
        health = responses["/healthz"]
        require(health.get("status") == "ok" and health.get("environment") == "candidate" and health.get("revision") == self.revision,
                "Browser endpoint is not this isolated candidate API")
        require(responses["/version.json"].get("revision") == self.revision, "Candidate frontend version differs from API")
        self.report["health"] = responses

    def error(self, source, message):
        self.report["errors"].append({"module": self.current_module, "source": source, "message": self.redact(message)})

    def observe(self, page):
        page.on("pageerror", lambda error: self.error("pageerror", error))

        def console(message):
            if message.type in {"warning", "error"} and ("[Vue warn]" in message.text or message.type == "error"):
                if "Failed to load resource:" not in message.text:
                    self.error("console", message.text)

        def request(value):
            parsed = urlsplit(value.url)
            if parsed.scheme in {"http", "https"} and f"{parsed.scheme}://{parsed.netloc}" != self.url:
                self.error("outside_candidate_origin", value.url)

        def failed(value):
            # A page intentionally supersedes in-flight reads when selecting a new
            # module. An aborted navigation is distinguished from a failed asset.
            if value.failure != "net::ERR_ABORTED":
                self.report["network_failures"].append({"module": self.current_module, "url": self.redact(value.url), "error": self.redact(value.failure)})

        def response(value):
            if value.status >= 400:
                path = urlsplit(value.url).path
                # Selecting a module/scenario first sends the previous/default
                # input. Only schema/business 1001 errors may precede our explicit
                # request; every explicit fixture response is checked below.
                if path.startswith("/api/v1/developer/modules/") and path.endswith("/preview") and value.status < 500:
                    try:
                        if value.json().get("code") == 1001:
                            return
                    except Exception:  # noqa: BLE001 - Non-JSON responses are hard failures.
                        pass
                self.error("http", f"{value.status} {path}")

        page.on("console", console)
        page.on("request", request)
        page.on("requestfailed", failed)
        page.on("response", response)

    @staticmethod
    def response_data(response):
        value = response.json()
        require(response.ok and value.get("code") == 0, f"Backend rejected {urlsplit(response.url).path}: HTTP {response.status}")
        return value["data"]

    def login(self):
        from playwright.sync_api import expect
        page = self.page
        page.goto(self.url + "/developer", timeout=self.remaining(30000))
        page.locator('input[name="account"]').fill(self.account)
        page.locator('input[name="password"]').fill(self.password)
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/app/auth/login", timeout=self.remaining()) as event:
            page.get_by_role("button", name="登录并进入", exact=True).click()
        account = self.response_data(event.value)
        require(account.get("role") == "admin", "Browser account must be a candidate-only administrator")
        self.secrets.append(account["token"])
        page.wait_for_url(self.url + "/", timeout=self.remaining())
        page.goto(self.url + "/developer", timeout=self.remaining())
        expect(page.get_by_role("heading", name="模块管理", exact=True)).to_be_visible(timeout=self.remaining())
        identity = self.response_data(page.request.get(self.url + "/api/v1/developer/context", headers={"Authorization": "Bearer " + account["token"]}, timeout=self.remaining()))
        require(identity.get("user_id") == self.account and identity.get("environment") == "candidate" and identity.get("revision") == self.revision,
                "Browser preview identity/environment differs from the verified dataflow context")
        response = page.request.get(self.url + "/api/v1/developer/modules", headers={"Authorization": "Bearer " + account["token"]}, timeout=self.remaining())
        modules = match_module_coverage(self.expected, self.response_data(response), self.revision)
        self.report["login"] = {"passed": True, "role": "admin", "synthetic": True}
        return modules

    def assert_no_renderer_fault(self):
        from playwright.sync_api import expect
        expect(self.page.get_by_role("alert").filter(has_text=re.compile("组件暂时无法显示|当前构建缺少"))).to_have_count(0, timeout=self.remaining())

    def surface(self, selector, *, detail=False):
        payload = {"selector": selector, "detail": detail}
        self.page.wait_for_function("args => (" + SURFACE + ")(args).count > 0", arg=payload, timeout=self.remaining())
        self.assert_no_renderer_fault()
        return self.page.evaluate(SURFACE, payload)

    def layout(self):
        result = self.page.evaluate("({page:document.documentElement.scrollWidth,viewport:innerWidth})")
        require(result["page"] <= result["viewport"] + 1, "Module preview causes horizontal page overflow")
        return result

    def fixture(self, module, fixture, size):
        from playwright.sync_api import expect
        manifest = module["manifest"]
        module_id = manifest["id"]
        page = self.page
        page.set_default_timeout(self.remaining())
        page.set_viewport_size(SIZES[size])
        page.locator(".developer > nav").get_by_role("button", name="调试预览", exact=True).click()
        controls = page.locator(".preview-controls")
        controls.get_by_label("模块", exact=True).select_option(module_id)
        controls.get_by_label("数据模式", exact=True).select_option("fixture")
        controls.get_by_label("场景", exact=True).select_option(fixture)
        run = page.locator(".module-host > .module-input > button")
        expect(run).to_be_enabled(timeout=self.remaining())
        inputs = self.expected[module_id]["inputs"][fixture]
        page.locator(".module-host > .module-input textarea").fill(json.dumps(inputs, ensure_ascii=False))
        endpoint = f"/api/v1/developer/modules/{module_id}/preview"
        with page.expect_response(lambda response: urlsplit(response.url).path == endpoint and
                response.request.post_data_json == {"mode": "fixture", "fixture": fixture, "input": inputs, "expected_version": manifest["version"]}, timeout=self.remaining()) as event:
            run.click()
        response = event.value
        payload = response.json()
        require(response.request.post_data_json["input"] == inputs, "Preview did not submit verified fixture input")
        expect(run).to_be_enabled(timeout=self.remaining())
        host = page.locator(".module-host")
        evidence = {"fixture": fixture, "viewport": size, "passed": False, "input": inputs, "http_status": response.status}
        self.assert_no_renderer_fault()
        if fixture == "error":
            require(response.status < 500 and payload.get("code") == 1001 and payload.get("message"), "Error fixture must produce an explicit business error, not success or a server crash")
            expected_error = self.expected[module_id].get("fixture_error")
            if expected_error:
                require(payload["message"] == expected_error, "Browser error differs from verified fixture error")
            expect(host.locator(".module-error")).to_contain_text(payload["message"], timeout=self.remaining())
            expect(host.locator(".module-open")).to_have_count(0, timeout=self.remaining())
            expect(host.locator(".module-conversation-open")).to_have_count(0, timeout=self.remaining())
            if manifest["kind"] == "tool":
                expect(host.get_by_label("技能返回 JSON", exact=True)).to_have_count(0, timeout=self.remaining())
            evidence["business_error"] = payload["message"]
        else:
            result = self.response_data(response)
            require(result == self.expected[module_id]["fixtures"][fixture], f"{module_id}.{fixture}: browser result differs from validated dataflow output")
            expect(host.locator(".module-error")).to_have_count(0, timeout=self.remaining())
            if manifest["kind"] == "tool":
                returned = host.get_by_label("技能返回 JSON", exact=True)
                expect(returned).to_be_visible(timeout=self.remaining())
                require(json.loads(returned.inner_text()) == result, "Skill JSON display differs from actual response")
                expect(host.locator(".module-open")).to_have_count(0, timeout=self.remaining())
                evidence["surface"] = "skill_json"
            else:
                evidence["card"] = self.surface(".module-host [data-module-surface='card']")
                debug = host.locator(":scope > details").filter(has=page.locator("summary", has_text="调试结果与日志"))
                if debug.get_attribute("open") is None:
                    debug.locator(":scope > summary").click()
                require(json.loads(debug.locator(":scope > pre").inner_text()) == result, "Preview JSON differs from actual response")
                evidence["surface"] = "card"
            evidence["result"] = result
            if manifest.get("detail"):
                host.locator(":scope > .module-open").click()
                dialog = page.locator(".module-detail-dialog")
                expect(dialog).to_be_visible(timeout=self.remaining())
                try:
                    evidence["detail"] = self.surface(".module-detail-dialog [data-module-surface='detail']", detail=True)
                    evidence["detail_layout"] = self.layout()
                    evidence["detail_screenshot"] = self.screenshot(f"{module_id}-{fixture}-{size}-detail")
                finally:
                    dialog.locator(":scope > .module-head > button").click()
            if manifest.get("conversation"):
                host.locator(":scope > .module-conversation-open").click()
                dialog = page.locator(".module-conversation-dialog")
                expect(dialog).to_be_visible(timeout=self.remaining())
                try:
                    evidence["conversation"] = self.surface(".module-conversation-dialog [data-module-surface='conversation']", detail=True)
                    evidence["conversation_layout"] = self.layout()
                    evidence["conversation_screenshot"] = self.screenshot(f"{module_id}-{fixture}-{size}-conversation")
                finally:
                    dialog.locator(":scope > .module-head > button").click()
        evidence["layout"] = self.layout()
        page.wait_for_timeout(min(150, self.remaining()))
        evidence["screenshot"] = self.screenshot(f"{module_id}-{fixture}-{size}")
        self.assert_no_renderer_fault()
        evidence["passed"] = True
        return evidence

    def run(self):
        from playwright.sync_api import sync_playwright
        try:
            self.health()
            with sync_playwright() as playwright:
                launch = {"headless": True, "timeout": self.remaining(30000)}
                if sys.platform == "win32":
                    launch["channel"] = "msedge"
                else:
                    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or playwright.chromium.executable_path
                    require(chromium and Path(chromium).is_file(), "An installed Chromium executable is required on this host")
                    launch["executable_path"] = chromium
                browser = playwright.chromium.launch(**launch)
                self.report["browser"] = {"version": browser.version, "channel": launch.get("channel", "chromium")}
                try:
                    self.context = browser.new_context(viewport=SIZES["desktop"], service_workers="block")
                    self.page = self.context.new_page()
                    self.observe(self.page)
                    modules = self.login()
                    for module_id, module in modules.items():
                        self.current_module = module_id
                        item = {"version": module["manifest"]["version"], "kind": module["manifest"]["kind"],
                            "enabled_at_start": module["effective_enabled"], "passed": False, "checks": [],
                            "components": {slot: module["manifest"].get(slot) for slot in ("card", "detail", "conversation")}}
                        self.report["modules"][module_id] = item
                        for size in SIZES:
                            for fixture in FIXTURES:
                                try:
                                    item["checks"].append(self.fixture(module, fixture, size))
                                except Exception as exc:  # noqa: BLE001 - Keep the failing module, fixture and screenshot.
                                    failed = {"fixture": fixture, "viewport": size, "passed": False, "error": self.redact(exc)}
                                    try:
                                        failed["screenshot"] = self.screenshot(f"{module_id}-{fixture}-{size}-FAILED")
                                    except Exception as diagnostic:  # noqa: BLE001 - Screenshot failure cannot hide the test failure.
                                        failed["screenshot_error"] = self.redact(diagnostic)
                                    item["checks"].append(failed)
                                    self.save()
                                    raise
                                self.save()
                        item["passed"] = True
                        self.save()
                    require(not self.report["errors"] and not self.report["network_failures"], "Browser runtime or network errors were observed")
                    require(set(self.report["modules"]) == set(self.expected), "Browser coverage is incomplete")
                    self.report["passed"] = True
                finally:
                    browser.close()
        except Exception as exc:  # noqa: BLE001 - A gate always returns durable failure evidence.
            self.report["error"] = self.redact(exc)
        finally:
            self.report["finished_at"] = time.time()
            self.save()
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dataflow-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    try:
        dataflow = json.loads(args.dataflow_report.read_text(encoding="utf-8"))
        report = BrowserGate(args.url, args.revision, dataflow, args.output.resolve(), args.timeout).run()
    except Exception as exc:  # noqa: BLE001 - Dependency/configuration failure must be a failed gate.
        report = {"gate": "browser", "passed": False, "revision": args.revision, "error": str(exc)}
        atomic_report(args.output.resolve(), report)
    print(json.dumps({"passed": report["passed"], "report": str(args.output.resolve()), "gate": "browser", "error": report.get("error", "")}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
