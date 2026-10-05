"""Safety/reporting checks for the opt-in real Docker recovery acceptance tool."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("tested_recovery_acceptance", ROOT / "deploy/accept_bluegreen_recovery.py")
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)
REVISION = "a" * 40


def ports():
    return {"blue_web": 25176, "blue_api": 28016, "green_web": 25177,
            "green_api": 28017, "gateway_web": 25175, "gateway_api": 28015}


def test_recovery_compose_has_private_database_network_and_ports():
    value = acceptance.isolated_spec(ports())
    assert value["networks"] == {"shared": {}}
    services = value["services"]
    assert "acceptance_api" not in services
    assert "postgres" in services and "redis" in services
    assert "ports" not in services["postgres"] and "ports" not in services["redis"]
    assert "volumes" not in value
    for slot in ("blue", "green"):
        assert services[f"api_{slot}"]["environment"]["ZHIYIN_RUN_BACKGROUND_WORKERS"] == "0"
        assert services[f"api_{slot}"]["depends_on"]["postgres"] == {"condition": "service_healthy"}
    assert services["background"]["environment"]["ZHIYIN_RUN_BACKGROUND_WORKERS"] == "1"
    assert "ports" not in services["background"]
    for service in services.values():
        assert service["networks"] == ["shared"]
        for binding in service.get("ports", []):
            assert binding.startswith("127.0.0.1:")
            assert int(binding.split(":")[1]) not in acceptance.PROTECTED_PORTS


@pytest.mark.parametrize("port", sorted(acceptance.PROTECTED_PORTS) + [0, 80, 65536])
def test_recovery_compose_rejects_protected_or_invalid_ports(port):
    with pytest.raises(RuntimeError, match="ports"):
        acceptance.isolated_spec({**ports(), "gateway_api": port})


def test_recovery_compose_rejects_duplicate_ports():
    with pytest.raises(RuntimeError, match="distinct"):
        acceptance.isolated_spec({**ports(), "gateway_api": 25175})


def test_port_allocator_never_allocates_existing_application_ports():
    selected = acceptance.allocate_ports()
    assert len(selected) == 6 and len(set(selected.values())) == 6
    assert not set(selected.values()).intersection(acceptance.PROTECTED_PORTS)


def baseline(tmp_path, monkeypatch):
    route = {"slot": "green", "revision": REVISION, "generation": 12}
    directory = tmp_path / "bluegreen"
    directory.mkdir()
    journal = {"active_slot": "green", "active_revision": REVISION, "generation": 12, "pending": None,
        "slots": {"green": {"revision": REVISION, "api_image": "sha256:" + "1" * 64, "web_image": "sha256:" + "2" * 64}}}
    path = directory / "deployment.json"
    path.write_text(json.dumps(journal), encoding="utf-8")

    def request(address, path, **kwargs):
        assert kwargs["timeout"] <= 3
        if path == "/__platform_route":
            return route.copy()
        if path == "/version.json":
            return {"revision": REVISION}
        return {"revision": REVISION, "status": "ok", "environment": "staging"}

    monkeypatch.setattr(acceptance.base, "request", request)
    return {"state_directory": str(tmp_path)}, journal, path, request


def test_live_baseline_is_read_only_and_requires_matching_route(tmp_path, monkeypatch):
    config, journal, path, _ = baseline(tmp_path, monkeypatch)
    before = path.read_bytes()
    assert acceptance.live_snapshot(config)["route"]["generation"] == 12
    assert path.read_bytes() == before
    journal["generation"] = 13
    path.write_text(json.dumps(journal), encoding="utf-8")
    with pytest.raises(RuntimeError, match="persisted baseline"):
        acceptance.live_snapshot(config)


def test_live_baseline_refuses_running_release(tmp_path, monkeypatch):
    config, journal, path, _ = baseline(tmp_path, monkeypatch)
    journal["pending"] = {"job_id": "in-progress"}
    path.write_text(json.dumps(journal), encoding="utf-8")
    with pytest.raises(RuntimeError, match="idle"):
        acceptance.live_snapshot(config)


def test_live_baseline_refuses_wrong_frontend_revision(tmp_path, monkeypatch):
    config, _, _, request = baseline(tmp_path, monkeypatch)
    monkeypatch.setattr(acceptance.base, "request", lambda address, path, **kwargs:
        {"revision": "b" * 40} if path == "/version.json" else request(address, path, **kwargs))
    with pytest.raises(RuntimeError, match="frontend"):
        acceptance.live_snapshot(config)


def test_failed_http_sample_is_retained_as_failure(monkeypatch):
    def failure(*args, **kwargs):
        raise TimeoutError("injected connection timeout")

    monkeypatch.setattr(acceptance.base, "request", failure)
    ex = SimpleNamespace(web="http://127.0.0.1:25175", target="http://127.0.0.1:28015", redact=str)
    row = acceptance.HealthMonitor(ex, REVISION).sample()
    assert row["passed"] is False
    assert "timeout" in row["error"]


def test_failed_switch_keeps_observed_http_evidence(monkeypatch):
    class FailedMonitor:
        thread = SimpleNamespace(start=lambda: None)

        def __init__(self, executor, revision):
            pass

        def wait_samples(self, count):
            raise RuntimeError("observer could not reach gateway")

        def finish(self):
            return {"samples": [{"passed": False, "error": "actual HTTP timeout"}], "count": 1, "failed_count": 1}

    monkeypatch.setattr(acceptance, "HealthMonitor", FailedMonitor)
    rollout = SimpleNamespace(ex=SimpleNamespace(redact=str))
    result = acceptance.successful_switch(rollout, {"revision": REVISION})
    assert result["passed"] is False
    assert result["health"]["samples"][0]["error"] == "actual HTTP timeout"
    assert result["error"] == "observer could not reach gateway"


def test_local_probe_cannot_claim_upload_or_build_acceptance():
    job = acceptance.probe_job(REVISION)
    assert job["acceptance_scope"] == "runtime_recovery"
    assert "accepted_artifacts" not in job["result"]
    assert "version_id" not in job["result"]
    ex = object.__new__(acceptance.AcceptanceExecutor)
    ex.job = job
    ex.assert_authorized()
    with pytest.raises(RuntimeError, match="source gates"):
        ex.gates(Path("unused"))
    with pytest.raises(RuntimeError, match="dataflow"):
        ex.acceptance(Path("unused"), REVISION)
    ex.job = {**job, "acceptance_scope": "external_release"}
    with pytest.raises(RuntimeError, match="local recovery"):
        ex.assert_authorized()


def test_preflight_failure_persists_report_without_creating_docker_resources(tmp_path, monkeypatch):
    def not_ready(config):
        raise RuntimeError("gateway is not deployed")

    monkeypatch.setattr(acceptance, "live_snapshot", not_ready)
    output = tmp_path / "report.json"
    result = acceptance.run_acceptance({}, output)
    assert result["passed"] is False
    assert result["error"] == "gateway is not deployed"
    assert "project" not in result and "restored" not in result
    assert json.loads(output.read_text(encoding="utf-8")) == result
