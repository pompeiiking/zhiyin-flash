"""Browser-gate boundaries; real Edge/Chromium execution is a separate host gate."""
import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("tested_module_browser_gate", ROOT / "deploy/module_browser_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
REVISION = "a" * 40


def report():
    return {"revision": REVISION, "passed": True, "configuration_restored": True, "preview_user_id": "df_aaaaaaaaaaaa_one",
        "modules": {"new_skill": {"version": "0.1.2", "kind": "tool", "passed": True,
            "inputs": {"normal": {"expected_total": 2}, "empty": {"expected_total": 0}, "error": {}},
            "fixtures": {fixture: {"data": {"total": total}, "module_version": "0.1.2"} for fixture, total in (("normal", 2), ("empty", 0))}}}}


def installed():
    return [{"manifest": {"id": "new_skill", "version": "0.1.2", "kind": "tool"}, "effective_enabled": False,
             "source_revision": REVISION}]


def test_candidate_web_is_the_only_service_exposed_to_host():
    overlay = gate.candidate_web_overlay()
    assert set(overlay["services"]) == {"acceptance_web"}
    web = overlay["services"]["acceptance_web"]
    assert web["networks"] == ["acceptance", "browser_access"]
    assert web["profiles"] == ["acceptance"]
    assert web["environment"]["PLATFORM_SLOT_API"] == "acceptance_api"
    assert web["ports"] == ["127.0.0.1:${PLATFORM_ACCEPTANCE_WEB_PORT:?Set private browser port}:80"]
    assert overlay["networks"] == {"browser_access": {}}
    assert "acceptance" not in overlay["networks"]  # Original API/DB network stays internal.
    nginx = gate.candidate_nginx_template()
    assert "connect-src 'self'" in nginx and "default-src 'self'" in nginx
    assert "proxy_pass http://${PLATFORM_SLOT_API}:8000" in nginx


@pytest.mark.parametrize("url", [f"http://127.0.0.1:{port}" for port in sorted(gate.PROTECTED_PORTS)] + [
    "http://127.0.0.1", "https://127.0.0.1:29000", "http://localhost:29000", "http://example.org:29000",
    "http://user:secret@127.0.0.1:29000", "http://127.0.0.1:29000/api", "http://127.0.0.1:29000?port=5173",
    "http://127.0.0.1:29000/#live", "http://127.0.0.1:80", "http://127.0.0.1:99999"])
def test_gate_rejects_live_or_non_candidate_origins(url):
    with pytest.raises((ValueError, RuntimeError)):
        gate.candidate_origin(url)


def test_random_candidate_port_is_loopback_unreserved():
    port = gate.allocate_web_port([29000])
    assert port != 29000 and port not in gate.PROTECTED_PORTS
    assert gate.candidate_origin(f"http://127.0.0.1:{port}/") == f"http://127.0.0.1:{port}"


@pytest.mark.parametrize("change", ["inputs", "empty", "revision", "restoration", "module_passed", "preview_identity", "fixture_version"])
def test_report_cannot_skip_inputs_version_identity_or_acceptance(change):
    value = report()
    item = value["modules"]["new_skill"]
    if change == "inputs":
        item.pop("inputs")
    elif change == "empty":
        item["inputs"].pop("empty")
    elif change == "revision":
        value["revision"] = "b" * 40
    elif change == "restoration":
        value["configuration_restored"] = False
    elif change == "module_passed":
        item["passed"] = False
    elif change == "preview_identity":
        value["preview_user_id"] = "admin"
    else:
        item["fixtures"]["normal"]["module_version"] = "0.1.1"
    with pytest.raises(RuntimeError):
        gate.dataflow_contract(value, REVISION)


def test_coverage_includes_disabled_tools_and_rejects_missing_new_modules():
    expected = gate.dataflow_contract(report(), REVISION)
    found = gate.match_module_coverage(expected, installed(), REVISION)
    assert found["new_skill"]["effective_enabled"] is False
    with pytest.raises(RuntimeError, match="every installed module"):
        gate.match_module_coverage(expected, [], REVISION)
    extra = copy.deepcopy(installed()[0])
    extra["manifest"]["id"] = "another_app"
    with pytest.raises(RuntimeError, match="every installed module"):
        gate.match_module_coverage(expected, [*installed(), extra], REVISION)


def test_browser_must_reuse_the_dataflow_user(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_BROWSER_ACCOUNT", "another_admin")
    monkeypatch.setenv("PLATFORM_BROWSER_PASSWORD", "private-test-password")
    with pytest.raises(RuntimeError, match="reuse"):
        gate.BrowserGate("http://127.0.0.1:29000", REVISION, report(), tmp_path / "result.json", 60)
    monkeypatch.setenv("PLATFORM_BROWSER_ACCOUNT", report()["preview_user_id"])
    browser = gate.BrowserGate("http://127.0.0.1:29000", REVISION, report(), tmp_path / "result.json", 60)
    assert browser.expected["new_skill"]["inputs"]["normal"] == {"expected_total": 2}
    assert browser.redact("private-test-password") == "[REDACTED]"


def test_browser_cannot_repeat_one_fixture_in_place_of_complete_coverage():
    checks = [{"passed": True, "fixture": fixture, "viewport": viewport} for fixture in gate.FIXTURES for viewport in gate.SIZES]
    value = {"gate": "browser", "rules_version": "1", "passed": True, "revision": REVISION, "no_api_mocking": True,
        "errors": [], "network_failures": [], "modules": {"new_skill": {"version": "0.1.2", "kind": "tool", "passed": True, "checks": checks}}}
    gate.validate_browser_result(value, report(), REVISION)
    value["modules"]["new_skill"]["checks"] = [checks[0]] * 6
    with pytest.raises(RuntimeError, match="coverage is incomplete"):
        gate.validate_browser_result(value, report(), REVISION)
