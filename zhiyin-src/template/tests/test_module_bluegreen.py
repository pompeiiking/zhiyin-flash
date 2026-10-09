"""Blue/green state-machine tests. Docker integration runs separately on the host."""
import copy
import importlib.util
import json
from pathlib import Path
import threading
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("tested_module_bluegreen", ROOT / "deploy/module_bluegreen.py")
bluegreen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bluegreen)

A, B, C = "a" * 40, "b" * 40, "c" * 40


def artifacts(revision):
    return {"revision": revision, "api_image": "sha256:" + revision[0] * 64,
            "web_image": "sha256:" + revision[0] * 64}


def candidate_report():
    return {"revision": B, "passed": True, "configuration_restored": True, "preview_user_id": "df_aaaaaaaaaaaa_one",
        "modules": {"disabled_skill": {"version": "1.0.0", "kind": "tool", "passed": True,
            "inputs": {fixture: {} for fixture in ("normal", "empty", "error")},
            "fixtures": {fixture: {"data": {}, "module_version": "1.0.0"} for fixture in ("normal", "empty")}}}}


class FakeExecutor:
    def __init__(self, root, **config):
        self.root, self.repo, self.env_file = root, root / "source", root / "private.env"
        self.config = {"bluegreen_observation_seconds": 0, "browser_python": sys.executable, **config}
        self.env, self.secrets, self.events, self.commands, self.updates = {}, [], [], [], []
        self.web, self.target = "http://127.0.0.1:5175", "http://127.0.0.1:8015"
        self.lost, self.stopping = threading.Event(), threading.Event()
        self.job = None
        self.observed = {"slot": "blue", "revision": A, "generation": 1}
        self.live_revision = A
        self.authorized = True

    def heartbeat(self):
        self.stopping.wait()

    def redact(self, text, **kwargs):
        return text

    def log(self, stage, message):
        self.events.append((stage, message))

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def assert_authorized(self):
        self.events.append(("authorization", self.authorized))
        if not self.authorized:
            raise RuntimeError("项目发布授权已撤销")

    def checkout(self, revision):
        self.events.append(("checkout", revision))
        return self.repo / revision

    def gates(self, checkout):
        self.events.append(("gates", str(checkout)))

    def compose(self, checkout, revision, *args):
        self.events.append(("legacy_compose", revision, args))
        return "built"

    def acceptance(self, checkout, revision):
        self.events.append(("acceptance", revision))
        return {"passed": True, "modules": ["application", "pure_skill"], "artifacts": artifacts(revision)}

    def actual_revision(self):
        return self.live_revision

    def wait_healthy(self, revision):
        self.events.append(("legacy_healthy", revision))
        self.live_revision = revision

    def run(self, args, **kwargs):
        args = [str(value) for value in args]
        self.commands.append((args, kwargs))
        if args[:3] == ["docker", "image", "inspect"]:
            return "sha256:" + args[-1][-1] * 64
        if args[:2] == ["docker", "inspect"]:
            return "healthy"
        if args[:2] == ["docker", "ps"]:
            return ""
        if any(value.endswith("module_browser_gate.py") for value in args):
            Path(args[args.index("--output") + 1]).write_text(json.dumps({"gate": "browser", "rules_version": "1",
                "passed": True, "revision": B, "no_api_mocking": True, "errors": [], "network_failures": [],
                "modules": {"disabled_skill": {"passed": True, "version": "1.0.0", "kind": "tool",
                    "checks": [{"passed": True, "fixture": fixture, "viewport": viewport}
                               for fixture in ("normal", "empty", "error") for viewport in ("desktop", "narrow")]}}}), encoding="utf-8")
            return "browser passed"
        if "ps" in args:
            return "candidate-api-id"
        if "scripts/module_dataflow_acceptance.py" in args:
            return "ZHIYIN_DATAFLOW_REPORT=" + json.dumps(candidate_report())
        if "cat" in args and "/tmp/module-dataflow-report.json" in args:
            return json.dumps(candidate_report())
        return ""


class SimulatedRollout(bluegreen.BlueGreenRollout):
    def __init__(self, executor):
        super().__init__(executor)
        self.fail_health = None
        self.fail_after_switch = False
        self.lose_after_switch = False
        self.concurrent_revision = None
        self.incompatible_workflows = False

    def acquire_workflow_lock(self, slot):
        rollout = self
        self.ex.events.append(("workflow_lock", slot))
        if self.incompatible_workflows:
            raise RuntimeError("已发布工作流 test_flow/node=read/module=action_progress/version=1.0.0 不兼容")

        class Guard:
            def assert_alive(self):
                if rollout.ex.lost.is_set():
                    raise RuntimeError("lease lost")

            def fence(self, revision):
                self.assert_alive()
                rollout.ex.events.append(("fence", revision))

            def close(self):
                rollout.ex.events.append(("workflow_unlock", slot))

        self.workflow_guard = Guard()

    def route(self):
        return copy.deepcopy(self.ex.observed)

    def compose(self, *args, **kwargs):
        self.ex.events.append(("slot_compose", args, kwargs))
        return ""

    def wait_healthy(self, slot, revision, *, public=False, timeout=180):
        self.ex.events.append(("health", slot, revision, public))
        if self.fail_health == (slot, public):
            raise RuntimeError("injected health failure")

    def smoke(self, slot):
        self.ex.events.append(("smoke", slot))
        if self.concurrent_revision:
            self.ex.observed["revision"] = self.concurrent_revision

    def prepare_route(self, *args):
        self.ex.events.append(("prepare_route", args))

    def switch(self, slot, revision, generation, previous_slot, *, start=False):
        self.ex.events.append(("switch", slot, revision))
        self.ex.observed = {"slot": slot, "revision": revision, "generation": generation}
        if self.lose_after_switch:
            self.ex.lost.set()
            raise RuntimeError("process lease lost")
        if self.fail_after_switch and revision == B:
            raise RuntimeError("injected post-switch failure")

    def background(self, slot):
        self.ex.events.append(("background", slot))


@pytest.fixture
def executor(tmp_path):
    ex = FakeExecutor(tmp_path)
    rollout = SimulatedRollout(ex)
    rollout.journal = {"schema": 1, "active_slot": "blue", "active_revision": A, "generation": 1,
        "slots": {"blue": artifacts(A)}, "artifacts": {A: artifacts(A)}, "successful": [A], "pending": None}
    rollout.save()
    return ex


def job(revision=B, *, kind="deploy", expected=A):
    return {"id": "1" * 32, "lease": "2" * 32, "commit": revision, "kind": kind,
            "result": {"expected_revision": expected}}


def test_generated_compose_preserves_data_services_and_isolates_candidate():
    value = json.loads((ROOT / "deploy/compose.bluegreen.yml").read_text(encoding="utf-8"))
    assert value == bluegreen.compose_spec()
    assert "volumes" not in value
    assert "postgres" not in value["services"] and "redis" not in value["services"]
    assert value["networks"]["shared"]["external"]
    assert value["networks"]["acceptance"]["internal"]
    for name in ("api_blue", "api_green", "acceptance_api"):
        assert value["services"][name]["environment"]["ZHIYIN_RUN_BACKGROUND_WORKERS"] == "0"
    assert value["services"]["background"]["environment"]["ZHIYIN_RUN_BACKGROUND_WORKERS"] == "1"
    assert "ports" not in value["services"]["background"]
    candidate = value["services"]["acceptance_api"]
    assert candidate["networks"] == ["acceptance"] and "ports" not in candidate
    assert candidate["environment"]["ZHIYIN_DATAFLOW_ISOLATED"] == "1"
    assert candidate["environment"]["ZHIYIN_LLM_API_KEY"] == "candidate-check-only"


@pytest.mark.parametrize("overrides", [{"blue_web_port": 5173}, {"blue_api_port": 8014}, {"green_api_port": 8016}, {"blue_web_port": 65536}])
def test_candidate_ports_cannot_collide_with_existing_services(tmp_path, overrides):
    with pytest.raises(ValueError):
        bluegreen.BlueGreenRollout(FakeExecutor(tmp_path, **overrides))


def test_gateway_switches_api_and_web_together_and_retains_old_asset_fallback():
    text = bluegreen.gateway_config("green", B, 2, "blue")
    assert "http://api_green:8000" in text and "http://web_green:80" in text
    assert "set $previous_web web_blue:80" in text
    assert '"revision":"' + B + '"' in text
    assert "proxy_buffering off" in text and "listen 8000" in text
    for slot, revision in (("blue; injected", A), ("blue", "main")):
        with pytest.raises(ValueError):
            bluegreen.gateway_config(slot, revision, 1)


def test_gateway_config_is_validated_before_replacing_live_file(executor):
    rollout = bluegreen.BlueGreenRollout(executor)
    original = bluegreen.gateway_config("blue", A, 1)
    (rollout.gateway / "default.conf").write_text(original, encoding="utf-8")
    run = executor.run

    def fail_validation(args, **kwargs):
        if "-t" in args and "nginx" in args:
            raise RuntimeError("invalid nginx config")
        return run(args, **kwargs)

    executor.run = fail_validation
    with pytest.raises(RuntimeError, match="invalid nginx"):
        rollout.switch("green", B, 2, "blue")
    assert (rollout.gateway / "default.conf").read_text(encoding="utf-8") == original
    assert not any("reload" in args for args, _ in executor.commands)


def test_gateway_switch_persists_one_matching_route_for_both_ports(executor):
    rollout = bluegreen.BlueGreenRollout(executor)
    executor.request = lambda *args, **kwargs: {"slot": "green", "revision": B, "generation": 2}
    rollout.switch("green", B, 2, "blue")
    text = (rollout.gateway / "default.conf").read_text(encoding="utf-8")
    assert text.count('"revision":"' + B + '"') == 2
    assert not (rollout.gateway / "route.pending").exists()
    command_args = [args for args, _ in executor.commands]
    assert next(i for i, args in enumerate(command_args) if "-t" in args) < next(
        i for i, args in enumerate(command_args) if "reload" in args)


def test_cutover_occurs_only_after_candidate_health_and_real_data_acceptance(executor):
    rollout = SimulatedRollout(executor)
    rollout.execute(job())
    assert executor.observed["revision"] == B
    assert executor.updates[-1]["status"] == "succeeded"
    names = [item[0] for item in executor.events]
    assert names.index("acceptance") < names.index("smoke") < names.index("switch") < names.index("background")
    assert names.index("smoke") < names.index("workflow_lock") < names.index("switch") < names.index("fence") < names.index("background") < names.index("workflow_unlock")
    assert ("fence", B) in executor.events
    assert rollout.load()["previous_slot"] == "blue"
    assert all("stop" not in event[1] for event in executor.events if event[0] == "slot_compose")


def test_failed_candidate_does_not_switch_current_traffic(executor):
    rollout = SimulatedRollout(executor)
    rollout.fail_health = ("green", False)
    rollout.execute(job())
    assert executor.observed["revision"] == A
    assert executor.updates[-1]["status"] == "failed"
    assert not any(item[0] == "switch" for item in executor.events)
    assert rollout.load()["pending"] is None


def test_failed_switch_restores_previous_route_and_background(executor):
    rollout = SimulatedRollout(executor)
    rollout.fail_after_switch = True
    rollout.execute(job())
    assert executor.observed["revision"] == A
    assert executor.updates[-1]["status"] == "rolled_back"
    assert ("background", "blue") in executor.events
    assert rollout.load()["active_revision"] == A
    assert ("fence", A) in executor.events
    assert executor.events[-1][0] == "workflow_unlock"


def test_executor_interruption_after_switch_resumes_from_actual_route(executor):
    interrupted = SimulatedRollout(executor)
    interrupted.lose_after_switch = True
    interrupted.execute(job())
    assert executor.events[-1][0] == "workflow_unlock"
    assert executor.observed["revision"] == B
    assert interrupted.load()["active_revision"] == A
    assert interrupted.load()["pending"]["phase"] == "switching"
    resumed = SimulatedRollout(executor)
    resumed.execute(job())
    assert executor.updates[-1]["stage"] == "reconciled"
    assert resumed.load()["active_revision"] == B and resumed.load()["pending"] is None
    assert sum(event[0] == "switch" for event in executor.events) == 1
    assert sum(event[0] == "workflow_lock" for event in executor.events) == 2


def test_incompatible_published_workflow_preserves_active_slot(executor):
    rollout = SimulatedRollout(executor)
    rollout.incompatible_workflows = True
    rollout.execute(job())
    assert executor.observed["revision"] == A
    assert executor.updates[-1]["status"] == "failed"
    assert not any(event[0] in {"switch", "fence", "background"} for event in executor.events)
    assert any("action_progress" in event[1] for event in executor.events if event[0] == "failed")
    assert rollout.load()["pending"] is None


def test_environment_changed_since_acceptance_is_rejected_without_build(executor):
    rollout = SimulatedRollout(executor)
    rollout.execute(job(expected=C))
    assert executor.updates[-1]["status"] == "failed"
    assert not any(event[0] in {"gates", "switch"} for event in executor.events)


def test_environment_changed_during_checks_is_not_overwritten(executor):
    rollout = SimulatedRollout(executor)
    rollout.concurrent_revision = C
    rollout.execute(job())
    assert executor.observed["revision"] == C
    assert executor.updates[-1]["status"] == "failed"
    assert not any(event[0] == "switch" for event in executor.events)


def test_check_job_executes_dataflow_without_starting_shared_database_slot(executor):
    rollout = SimulatedRollout(executor)
    rollout.execute(job(kind="check"))
    assert executor.updates[-1]["stage"] == "dataflow_checked"
    assert executor.observed["revision"] == A
    assert not any(event[0] in {"smoke", "switch", "slot_compose"} for event in executor.events)


def uploaded_job():
    value = job()
    value["result"].update(version_id="d" * 32, digest="e" * 64, rules_version="3", accepted_artifacts=artifacts(B))
    return value


def test_uploaded_release_uses_exact_accepted_images_without_rebuilding(executor):
    rollout = SimulatedRollout(executor)
    rollout.execute(uploaded_job())
    assert executor.updates[-1]["status"] == "succeeded"
    assert rollout.load()["slots"]["green"] == artifacts(B)
    assert not any(event[0] in {"gates", "legacy_compose", "acceptance"} for event in executor.events)
    assert any(event[0] == "smoke" for event in executor.events)


@pytest.mark.parametrize("corrupt", ["missing_artifacts", "missing_version", "wrong_rule", "missing_digest",
                                    "wrong_revision", "image_tag", "missing_image"])
def test_incomplete_accepted_marker_fails_closed_without_fallback_build(executor, corrupt):
    value = uploaded_job()
    metadata = value["result"]
    if corrupt == "missing_artifacts":
        metadata.pop("accepted_artifacts")
    elif corrupt == "missing_version":
        metadata.pop("version_id")
    elif corrupt == "wrong_rule":
        metadata["rules_version"] = "2"
    elif corrupt == "missing_digest":
        metadata.pop("digest")
    elif corrupt == "wrong_revision":
        metadata["accepted_artifacts"]["revision"] = C
    elif corrupt == "image_tag":
        metadata["accepted_artifacts"]["api_image"] = "zhiyin-platform-api:latest"
    else:
        metadata["accepted_artifacts"].pop("web_image")
    rollout = SimulatedRollout(executor)
    rollout.execute(value)
    assert executor.updates[-1]["status"] == "failed"
    assert executor.observed["revision"] == A
    assert not any(event[0] in {"gates", "legacy_compose", "acceptance", "switch"} for event in executor.events)


def test_removed_accepted_image_is_not_reconstructed_from_the_same_commit(executor):
    original = executor.run

    def missing_image(args, **kwargs):
        if args[:3] == ["docker", "image", "inspect"]:
            raise RuntimeError("No such image")
        return original(args, **kwargs)

    executor.run = missing_image
    rollout = SimulatedRollout(executor)
    rollout.execute(uploaded_job())
    assert executor.updates[-1]["status"] == "failed"
    assert not any(event[0] in {"gates", "legacy_compose", "switch"} for event in executor.events)


def test_already_installed_commit_cannot_bypass_accepted_artifact_validation(executor):
    value = uploaded_job()
    value["commit"] = A
    value["result"].pop("accepted_artifacts")
    rollout = SimulatedRollout(executor)
    rollout.execute(value)
    assert executor.updates[-1]["status"] == "failed"


def test_same_commit_with_different_image_ids_is_not_claimed_as_installed(executor):
    value = uploaded_job()
    value["commit"] = A
    value["result"]["accepted_artifacts"]["revision"] = A
    rollout = SimulatedRollout(executor)
    rollout.execute(value)
    assert executor.updates[-1]["status"] == "failed"
    assert not any(event[0] in {"gates", "switch"} for event in executor.events)


def test_explicit_check_of_current_revision_runs_the_requested_checks(executor):
    rollout = SimulatedRollout(executor)
    rollout.execute(job(revision=A, kind="check"))
    assert executor.updates[-1]["stage"] == "dataflow_checked"
    assert any(event[0] == "gates" for event in executor.events)


def test_unknown_history_cannot_be_rebuilt_as_a_rollback(executor):
    rollout = SimulatedRollout(executor)
    rollout.execute(job(kind="rollback"))
    assert executor.updates[-1]["status"] == "failed"
    assert not any(event[0] == "gates" for event in executor.events)


def test_uninitialized_bluegreen_refuses_to_take_legacy_ports(tmp_path):
    executor = FakeExecutor(tmp_path)
    rollout = SimulatedRollout(executor)
    rollout.execute(job())
    assert executor.updates[-1]["status"] == "failed"
    assert executor.commands == []
    assert any(bluegreen.INCOMPLETE in event[1] for event in executor.events if event[0] == "failed")


def test_dataflow_uses_temporary_database_project_and_returns_report(executor):
    executor.job = job()
    rollout = bluegreen.BlueGreenRollout(executor)
    result = rollout.dataflow_gate(artifacts(B))
    assert result["passed"] and "disabled_skill" in result["modules"]
    compose_commands = [item for item in executor.commands if item[0][:2] == ["docker", "compose"]]
    for args, values in compose_commands:
        assert args[args.index("-p") + 1].startswith("zhiyin-module-candidate-")
        assert "ZHIYIN_POSTGRES_DSN" not in values["extra_env"]
    assert any("--volumes" in args and args[args.index("--profile") + 1:args.index("--profile") + 3] == ["acceptance", "down"]
               for args, _ in compose_commands if "--profile" in args)


def test_new_lease_gets_fresh_candidate_database_project(executor):
    executor.job = job()
    rollout = bluegreen.BlueGreenRollout(executor)
    rollout.dataflow_gate(artifacts(B))
    old = [args[args.index("-p") + 1] for args, _ in executor.commands if args[:2] == ["docker", "compose"]]
    executor.commands.clear()
    executor.job["lease"] = "3" * 32
    rollout.dataflow_gate(artifacts(B))
    new = [args[args.index("-p") + 1] for args, _ in executor.commands if args[:2] == ["docker", "compose"]]
    assert set(old).isdisjoint(new)


def test_failed_dataflow_report_blocks_deploy_and_cleans_only_candidate(executor):
    executor.job = job()
    original = executor.run

    def failed_report(args, **kwargs):
        if "cat" in args:
            executor.commands.append(([str(value) for value in args], kwargs))
            return json.dumps({"passed": False})
        return original(args, **kwargs)

    executor.run = failed_report
    rollout = bluegreen.BlueGreenRollout(executor)
    with pytest.raises(RuntimeError, match="未通过真实数据流"):
        rollout.dataflow_gate(artifacts(B))
    cleanup = [args for args, _ in executor.commands if "down" in args]
    assert len(cleanup) == 1
    assert cleanup[0][cleanup[0].index("-p") + 1].startswith("zhiyin-module-candidate-")
    assert cleanup[0][cleanup[0].index("--profile") + 1:cleanup[0].index("--profile") + 3] == ["acceptance", "down"]


def test_browser_gate_is_mandatory_uses_same_identity_and_cleans_overlay(executor):
    executor.job = job()
    rollout = bluegreen.BlueGreenRollout(executor)
    result = rollout.dataflow_gate(artifacts(B))
    assert result["passed"] and result["browser"]["passed"]
    browser = next((args, kwargs) for args, kwargs in executor.commands if any(value.endswith("module_browser_gate.py") for value in args))
    assert browser[1]["extra_env"]["PLATFORM_BROWSER_ACCOUNT"] == result["preview_user_id"]
    admin = next(args for args, _ in executor.commands if "scripts/module_admin.py" in args)
    assert result["preview_user_id"] in admin and "--reset-password" in admin and "--seed" not in admin
    cleanup = next(args for args, _ in executor.commands if "down" in args)
    assert cleanup.count("-f") == 2 and any(value.endswith("browser.compose.json") for value in cleanup)
    assert rollout.compose_overlays == []


def test_browser_render_failure_preserves_specific_module_fixture_error(executor):
    executor.job = job()
    original = executor.run

    def broken_browser(args, **kwargs):
        if any(str(value).endswith("module_browser_gate.py") for value in args):
            args = [str(value) for value in args]
            executor.commands.append((args, kwargs))
            Path(args[args.index("--output") + 1]).write_text(json.dumps({"passed": False, "error": "component failed",
                "modules": {"disabled_skill": {"passed": False, "checks": [
                    {"fixture": "empty", "viewport": "narrow", "passed": False, "error": "Vue render TypeError"}]}}}), encoding="utf-8")
            raise RuntimeError("command exited 1")
        return original(args, **kwargs)

    executor.run = broken_browser
    with pytest.raises(RuntimeError, match="disabled_skill/empty/narrow: Vue render TypeError"):
        bluegreen.BlueGreenRollout(executor).dataflow_gate(artifacts(B))
    dataflow = executor.root / "acceptance" / "jobs" / executor.job["id"] / executor.job["lease"] / "dataflow.json"
    assert json.loads(dataflow.read_text(encoding="utf-8"))["passed"] is False
    assert any("down" in args and "--profile" in args for args, _ in executor.commands)


def test_missing_browser_runtime_fails_before_starting_containers(executor):
    executor.job = job()
    executor.config.pop("browser_python")
    with pytest.raises(ValueError, match="browser_python"):
        bluegreen.BlueGreenRollout(executor).dataflow_gate(artifacts(B))
    assert executor.commands == []


def test_revoked_trust_stops_release_before_build(executor):
    executor.authorized = False
    rollout = SimulatedRollout(executor)
    rollout.execute(job())
    assert executor.updates[-1]["status"] == "failed"
    assert not any(event[0] in {"gates", "switch"} for event in executor.events)


def test_trust_revoked_after_smoke_prevents_candidate_activation(executor):
    rollout = SimulatedRollout(executor)
    original = rollout.smoke

    def revoke(slot):
        original(slot)
        executor.authorized = False

    rollout.smoke = revoke
    rollout.execute(job())
    assert executor.observed["revision"] == A
    # Recovery is allowed even though new activation is forbidden.
    assert not any(event[0] == "switch" and event[2] == B for event in executor.events)


def test_smoke_reads_candidate_url_and_never_updates_shared_policies(executor):
    executor.job = job()
    rollout = bluegreen.BlueGreenRollout(executor)
    requests = []

    def request(base, path, **kwargs):
        requests.append((base, path, kwargs))
        if path.endswith("/login"):
            return {"token": "synthetic"}
        if path.endswith("/developer/modules"):
            return [{"manifest": {"id": "pure_skill"}, "effective_enabled": True}]
        return {}

    executor.request = request
    rollout.smoke("green")
    assert all(base == "http://127.0.0.1:5177" for base, _, _ in requests)
    assert any(path.endswith("/pure_skill/data") for _, path, _ in requests)
    assert not any(path.endswith("/policy") for _, path, _ in requests)
    assert all("--seed" in args for args, _ in executor.commands if "scripts/module_admin.py" in args)


def test_initial_migration_can_prepare_new_compatible_baseline_without_stopping_old(executor):
    (executor.root / "bluegreen/deployment.json").unlink()
    rollout = SimulatedRollout(executor)
    rollout.prepare_migration(B)
    assert executor.live_revision == A
    assert rollout.load()["migration"] == {"revision": B, "previous_revision": A, "phase": "prepared"}
    assert not any(event[0] == "legacy_compose" for event in executor.events)


def test_first_migration_failure_restores_legacy_apps_without_touching_data(executor):
    (executor.root / "bluegreen/deployment.json").unlink()
    rollout = SimulatedRollout(executor)
    rollout.prepare_migration(B)
    rollout.fail_after_switch = True
    with pytest.raises(RuntimeError, match="post-switch"):
        rollout.activate_migration()
    commands = [event for event in executor.events if event[0] == "legacy_compose"]
    assert commands[0][2] == ("stop", "api", "web")
    assert commands[-1][1] == A
    assert commands[-1][2] == ("up", "-d", "--no-build", "api", "web")
    assert rollout.load()["migration"]["phase"] == "prepared"


def test_interrupted_first_migration_has_explicit_recovery_command(executor):
    (executor.root / "bluegreen/deployment.json").unlink()
    rollout = SimulatedRollout(executor)
    rollout.prepare_migration(B)
    rollout.journal["migration"]["phase"] = "handoff"
    rollout.save()
    restarted = SimulatedRollout(executor)
    restarted.recover_migration()
    assert restarted.load()["migration"]["phase"] == "prepared"
    assert ("legacy_healthy", A) in executor.events
