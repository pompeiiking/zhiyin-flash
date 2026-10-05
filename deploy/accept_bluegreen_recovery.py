"""Exercise real blue/green recovery in a disposable, isolated Docker project.

Scope: runtime health, routing, rollback and persisted-journal recovery using the
already accepted images from the live staging journal. This does not rerun source
checks, dataflow acceptance, upload authorization or model calls. Both test slots
have the same real revision; successful same-revision switching calls the actual
rollout primitives explicitly, while recovery uses BlueGreenRollout.execute.

Run only after the baseline gateway is deployed:
  python deploy/accept_bluegreen_recovery.py --config .platform/executor.json
The live application and database are read-only inputs. All injected failures,
synthetic accounts and containers belong to a unique private acceptance project.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import socket
import threading
import time
from pathlib import Path
from uuid import uuid4


HERE = Path(__file__).resolve().parent
PROTECTED_PORTS = {5173, 5174, 5175, 5176, 5177, 8000, 8014, 8015, 8016, 8017}
PROJECT_PREFIX = "zhiyin-recovery-acceptance-"


def load_tool(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_tool("recovery_acceptance_executor", "module_executor.py")
bg = load_tool("recovery_acceptance_bluegreen", "module_bluegreen.py")


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def allocate_ports():
    """Select six distinct loopback ports; Docker binding remains the final check."""
    sockets = []
    try:
        while len(sockets) < 6:
            handle = socket.socket()
            handle.bind(("127.0.0.1", 0))
            if handle.getsockname()[1] in PROTECTED_PORTS:
                handle.close()
                continue
            sockets.append(handle)
        values = [handle.getsockname()[1] for handle in sockets]
        return dict(zip(("blue_web", "blue_api", "green_web", "green_api", "gateway_web", "gateway_api"), values, strict=True))
    finally:
        for handle in sockets:
            handle.close()


def isolated_spec(ports):
    ensure(len(set(ports.values())) == 6 and all(isinstance(port, int) and 1024 <= port <= 65535 and port not in PROTECTED_PORTS for port in ports.values()),
           "Acceptance ports must be distinct and outside protected application ports")
    value = bg.compose_spec()
    services = value["services"]
    postgres = services.pop("acceptance_postgres")
    redis = services.pop("acceptance_redis")
    services.pop("acceptance_api")
    for service in (postgres, redis):
        service.pop("profiles", None)
        service["networks"] = ["shared"]
    postgres["environment"]["POSTGRES_PASSWORD"] = "${PLATFORM_DB_PASSWORD:?Set isolated password}"
    services.update(postgres=postgres, redis=redis)
    # Docker Desktop suppresses published host ports for internal networks.
    # A project-private bridge permits the real host HTTP probes without joining
    # the live database network; credentials remain synthetic and no model runs.
    value["networks"] = {"shared": {}}
    for name in ("api_blue", "api_green", "background"):
        services[name]["depends_on"] = {"postgres": {"condition": "service_healthy"}, "redis": {"condition": "service_healthy"}}
    for slot in bg.SLOTS:
        services[f"api_{slot}"]["ports"] = [f"127.0.0.1:{ports[slot + '_api']}:8000"]
        services[f"web_{slot}"]["ports"] = [f"127.0.0.1:{ports[slot + '_web']}:80"]
    services["gateway"]["ports"] = [f"127.0.0.1:{ports['gateway_web']}:80", f"127.0.0.1:{ports['gateway_api']}:8000"]
    services["gateway"]["stop_grace_period"] = "5s"
    return value


class AcceptanceExecutor(base.Executor):
    """Real host commands and HTTP, with local-only job events and bounded waits."""

    def __init__(self, config, deadline, revision):
        super().__init__(config)
        self.deadline, self.revision = deadline, revision
        self.events, self.updates = [], []
        self.web = config["acceptance_web"]
        self.target = config["acceptance_api"]

    def run(self, args, **kwargs):
        remaining = self.deadline - time.monotonic()
        ensure(remaining > 0, "Acceptance time budget exhausted")
        kwargs["timeout"] = min(float(kwargs.get("timeout", 90)), remaining, 90)
        return super().run(args, **kwargs)

    def update(self, **values):
        self.updates.append(copy.deepcopy(values))

    def log(self, stage, message):
        self.events.append({"stage": stage, "message": self.redact(str(message)), "time": time.time()})
        print(f"[recovery-acceptance:{stage}]", flush=True)

    def heartbeat(self):
        self.stopping.wait()

    def assert_authorized(self):
        ensure(self.job and self.job.get("acceptance_scope") == "runtime_recovery", "Only local recovery probe jobs are accepted")

    def checkout(self, revision):
        ensure(revision == self.revision, "Probe cannot introduce an unaccepted revision")
        return self.repo

    def gates(self, checkout):
        raise RuntimeError("Runtime acceptance must not rebuild or rerun source gates")

    def acceptance(self, checkout, revision):
        raise RuntimeError("Runtime acceptance must not claim dataflow acceptance")


class AcceptanceRollout(bg.BlueGreenRollout):
    def __init__(self, executor):
        super().__init__(executor)
        self.project = executor.config["acceptance_project"]
        ensure(self.project.startswith(PROJECT_PREFIX) and len(self.project) == len(PROJECT_PREFIX) + 16,
               "Refusing to use a non-acceptance Docker project")
        self.health_timeout = 60
        self.interrupt_after_public_health = False

    def wait_healthy(self, slot, revision, *, public=False, timeout=180):
        remaining = self.ex.deadline - time.monotonic()
        ensure(remaining > 0, "Acceptance time budget exhausted")
        try:
            super().wait_healthy(slot, revision, public=public, timeout=min(timeout, self.health_timeout, remaining))
        except RuntimeError:
            web = self.ex.web if public else self.slot_url(slot)
            api = self.ex.target if public else self.slot_url(slot, "api")
            diagnostics = []
            for address, path in ((web, "/healthz"), (api, "/healthz"), (web, "/version.json")):
                row = {"url": address + path}
                try:
                    response = self.request(address, path, timeout=2)
                    row["response"] = {key: response.get(key) for key in ("status", "revision", "environment")}
                except Exception as exc:  # noqa: BLE001 - Preserve concrete endpoint failures.
                    row["error"] = self.ex.redact(str(exc))
                diagnostics.append(row)
            self.log("health_diagnostics", json.dumps(diagnostics, ensure_ascii=False))
            raise
        if public and self.interrupt_after_public_health:
            self.interrupt_after_public_health = False
            self.ex.lost.set()
            raise RuntimeError("Injected lease loss after real post-switch health observation")

    def wait_service(self, service, *, project=None):
        deadline = min(self.ex.deadline, time.monotonic() + 60)
        while time.monotonic() < deadline:
            container = self.compose("ps", "-q", service, project=project).strip()
            if container:
                status = self.ex.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container]).strip()
                if status == "healthy":
                    return
                ensure(status != "unhealthy", f"Acceptance service unhealthy: {service}")
            ensure(not self.ex.lost.wait(1), "Acceptance lease lost")
        raise RuntimeError(f"Acceptance service timeout: {service}")


class HealthMonitor:
    def __init__(self, executor, revision):
        self.ex, self.revision = executor, revision
        self.samples = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def sample(self):
        row = {"at": time.time(), "passed": False}
        try:
            health = base.request(self.ex.web, "/healthz", timeout=1)
            api = base.request(self.ex.target, "/healthz", timeout=1)
            version = base.request(self.ex.web, "/version.json", timeout=1)
            route = base.request(self.ex.web, "/__platform_route", timeout=1)
            row.update(route=route, web_revision=health.get("revision"), api_revision=api.get("revision"),
                       frontend_revision=version.get("revision"))
            row["passed"] = all(result.get("status") == "ok" and result.get("environment") == "staging" and result.get("revision") == self.revision for result in (health, api)) and version.get("revision") == self.revision
        except Exception as exc:  # noqa: BLE001 - Failed HTTP samples must remain evidence.
            row["error"] = self.ex.redact(str(exc))
        return row

    def run(self):
        while not self.stop.is_set() and time.monotonic() < self.ex.deadline:
            self.samples.append(self.sample())
            self.stop.wait(.25)

    def wait_samples(self, count, slot=None):
        deadline = min(self.ex.deadline, time.monotonic() + 15)
        while time.monotonic() < deadline:
            if sum(1 for row in self.samples if slot is None or row.get("route", {}).get("slot") == slot) >= count:
                return
            time.sleep(.1)
        raise RuntimeError("Not enough real HTTP observations during switch")

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=5)
        ensure(not self.thread.is_alive(), "HTTP observer did not finish in time")
        return {"samples": self.samples, "count": len(self.samples), "failed_count": sum(not row["passed"] for row in self.samples),
                "interval_seconds": .25, "claim": "HTTP polling continuity only; no SSE or browser hot-reload claim"}


def container_evidence(rollout, service):
    identifier = rollout.compose("ps", "-a", "-q", service).strip()
    ensure(identifier and "\n" not in identifier, f"Expected exactly one {service} container")
    output = rollout.ex.run(["docker", "inspect", "--format",
        '{"id":"{{.Id}}","image":"{{.Image}}","status":"{{.State.Status}}","exit_code":{{.State.ExitCode}},"project":"{{index .Config.Labels "com.docker.compose.project"}}"}', identifier])
    result = json.loads(output)
    ensure(result["project"] == rollout.project, "Container is outside the isolated acceptance project")
    return result


def publication_evidence(rollout, slot, *, locked=False):
    """Read the disposable project's fence and actual PostgreSQL advisory locks."""
    code = """import asyncio,json,os,asyncpg
async def main():
 c=await asyncpg.connect(os.environ['ZHIYIN_POSTGRES_DSN'],timeout=5,command_timeout=5)
 try:
  revision=await c.fetchval('SELECT active_revision FROM biz_module_runtime_revision WHERE id=1')
  count=await c.fetchval("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=0 AND objid=741517501 AND mode='ExclusiveLock' AND granted")
  print(json.dumps({'revision':revision,'exclusive_locks':count}))
 finally: await c.close(timeout=5)
asyncio.run(main())
"""
    value = json.loads(rollout.compose("exec", "-T", f"api_{slot}", "python", "-c", code))
    ensure(value["revision"] == rollout.ex.revision, "Private workflow fence differs from the real active revision")
    ensure(value["exclusive_locks"] == (1 if locked else 0), "Workflow publication lock state is incorrect")
    return value


def probe_job(revision):
    return {"id": uuid4().hex, "lease": uuid4().hex, "kind": "deploy", "commit": revision,
            "result": {"expected_revision": revision}, "acceptance_scope": "runtime_recovery"}


def prepare_candidate(rollout, artifacts):
    before = rollout.reconcile()
    target = "green" if before["slot"] == "blue" else "blue"
    job = probe_job(artifacts["revision"])
    rollout.ex.job = job
    rollout.journal["slots"][target] = copy.deepcopy(artifacts)
    rollout.journal["pending"] = {"job_id": job["id"], "target_slot": target, "target_revision": artifacts["revision"],
        "previous_slot": before["slot"], "previous_revision": before["revision"], "generation": before["generation"] + 1,
        "phase": "starting"}
    rollout.save()
    rollout.compose("up", "-d", "--no-build", f"api_{target}", f"web_{target}")
    rollout.wait_healthy(target, artifacts["revision"])
    rollout.smoke(target)
    ensure(rollout.route() == before, "Preparing candidate changed the active route")
    return before, target, job


def switch_prepared(rollout, before, target, *, save_observing=True):
    rollout.acquire_workflow_lock(target)
    pending = rollout.journal["pending"]
    pending["phase"] = "switching"
    rollout.save()
    rollout.switch(target, before["revision"], pending["generation"], before["slot"])
    rollout.fence_workflow_revision(before["revision"])
    if save_observing:
        pending["phase"] = "observing"
        rollout.save()


def successful_switch(rollout, artifacts):
    monitor = HealthMonitor(rollout.ex, artifacts["revision"])
    before, target, failure, publication = None, None, None, None
    monitor.thread.start()
    try:
        monitor.wait_samples(3)
        before, target, _ = prepare_candidate(rollout, artifacts)
        switch_prepared(rollout, before, target)
        rollout.wait_healthy(target, artifacts["revision"], public=True)
        rollout.background(target)
        rollout.finish(target, artifacts["revision"], before["slot"], before["generation"] + 1)
        publication = publication_evidence(rollout, target, locked=True)
        monitor.wait_samples(3, target)
    except Exception as exc:  # noqa: BLE001 - Keep every failing HTTP sample in the final report.
        failure = rollout.ex.redact(str(exc))
    finally:
        if before is not None:
            rollout.release_workflow_lock()
        evidence = monitor.finish()
    result = {"passed": failure is None and evidence["count"] >= 6 and evidence["failed_count"] == 0,
              "before": before, "health": evidence}
    if result["passed"]:
        result.update(after=rollout.route(), candidate_api=container_evidence(rollout, f"api_{target}"),
                      candidate_web=container_evidence(rollout, f"web_{target}"), publication_while_held=publication,
                      publication_after_release=publication_evidence(rollout, target))
    else:
        result["error"] = failure or "HTTP continuity failed during healthy candidate switch"
    return result


def bad_start(rollout, artifacts):
    before = rollout.route()
    target = "green" if before["slot"] == "blue" else "blue"
    rollout.journal["slots"][target] = copy.deepcopy(artifacts)
    rollout.save()
    original = rollout.compose_file
    broken = json.loads(original.read_text(encoding="utf-8"))
    broken["services"][f"api_{target}"].update(command=["python", "-c", "raise SystemExit(79)"], restart="no")
    fault_file = rollout.root / "bad-start.compose.json"
    bg.atomic_json(fault_file, broken)
    try:
        rollout.compose_file = fault_file
        rollout.compose("up", "-d", "--no-build", "--no-deps", f"api_{target}")
        failure = ""
        try:
            rollout.wait_healthy(target, artifacts["revision"], timeout=6)
        except RuntimeError as exc:
            failure = str(exc)
        ensure(failure, "Deliberately broken API unexpectedly passed health")
        container = container_evidence(rollout, f"api_{target}")
        ensure(container["status"] == "exited" and container["exit_code"] == 79, "Startup failure injection was not observed in Docker")
        ensure(rollout.route() == before, "Bad startup changed the live route")
        rollout.wait_healthy(before["slot"], before["revision"], public=True)
        return {"passed": True, "before": before, "after": rollout.route(), "health_failure": failure, "failed_container": container}
    finally:
        rollout.compose_file = original
        rollout.compose("up", "-d", "--no-build", f"api_{target}", f"web_{target}")
        rollout.wait_healthy(target, artifacts["revision"])


def post_switch_failure(rollout, artifacts):
    before, target, job = prepare_candidate(rollout, artifacts)
    switch_prepared(rollout, before, target)
    switched = rollout.route()
    rollout.wait_healthy(target, artifacts["revision"], public=True)
    rollout.compose("stop", "-t", "5", f"api_{target}")
    stopped = container_evidence(rollout, f"api_{target}")
    ensure(stopped["status"] == "exited", "Post-switch API stop was not observed")
    prior_timeout = rollout.health_timeout
    rollout.health_timeout = 6
    try:
        rollout.execute(job)
    finally:
        rollout.health_timeout = prior_timeout
    ensure(rollout.ex.updates[-1].get("status") == "rolled_back", "Real post-switch failure did not enter executor rollback")
    after = rollout.route()
    ensure(after["slot"] == before["slot"] and after["generation"] > switched["generation"] and not rollout.journal.get("pending"),
           "Rollback did not restore the previous route and clear its journal")
    rollout.wait_healthy(before["slot"], artifacts["revision"], public=True)
    return {"passed": True, "before": before, "switched": switched, "after": after,
            "stopped_candidate": stopped, "executor_result": rollout.ex.updates[-1]}


def lease_recovery(rollout, artifacts):
    before, target, job = prepare_candidate(rollout, artifacts)
    switch_prepared(rollout, before, target, save_observing=False)
    switched = rollout.route()
    rollout.interrupt_after_public_health = True
    rollout.execute(job)
    ensure(rollout.ex.lost.is_set(), "Lease-loss injection did not trigger")
    pending = json.loads(rollout.journal_path.read_text(encoding="utf-8"))["pending"]
    ensure(pending and pending["phase"] == "switching", "Interrupted executor did not preserve its pending journal")
    fresh_executor = AcceptanceExecutor(rollout.ex.config, rollout.ex.deadline, artifacts["revision"])
    fresh = AcceptanceRollout(fresh_executor)
    resumed = {**job, "lease": uuid4().hex}
    fresh.execute(resumed)
    ensure(fresh_executor.updates[-1].get("status") == "succeeded" and fresh_executor.updates[-1].get("stage") == "reconciled",
           "Fresh executor did not reconcile the actual switched route")
    ensure(fresh.route() == switched and fresh.journal["active_slot"] == target and fresh.journal.get("pending") is None,
           "Restart recovery changed the route or retained an unfinished journal")
    fresh.wait_healthy(target, artifacts["revision"], public=True)
    for service in ("api", "web"):
        ensure(container_evidence(fresh, f"{service}_{target}")["image"] == artifacts[f"{service}_image"], "Recovered container image differs from accepted image")
    rollout.ex.lost.clear()
    rollout.journal = fresh.journal
    rollout.ex.events.extend(fresh_executor.events)
    return {"passed": True, "before": before, "interrupted_route": switched, "pending_after_interruption": pending,
            "new_lease": resumed["lease"], "old_lease": job["lease"], "after": fresh.route(), "executor_result": fresh_executor.updates[-1]}


def live_snapshot(config):
    journal_path = Path(config["state_directory"]) / "bluegreen" / "deployment.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    ensure(journal.get("active_slot") in bg.SLOTS and not journal.get("pending"), "Live blue/green baseline must be initialized and idle")
    route = base.request("http://127.0.0.1:5175", "/__platform_route", timeout=3)
    ensure(route == {"slot": journal["active_slot"], "revision": journal["active_revision"], "generation": journal["generation"]},
           "Live gateway differs from the persisted baseline")
    artifacts = journal["slots"][route["slot"]]
    ensure(artifacts["revision"] == route["revision"] and bg.REVISION.fullmatch(route["revision"]), "Live revision is invalid")
    ensure(all(bg.IMAGE.fullmatch(artifacts.get(f"{service}_image", "")) for service in ("api", "web")), "Live image IDs are invalid")
    for address in ("http://127.0.0.1:5175", "http://127.0.0.1:8015"):
        health = base.request(address, "/healthz", timeout=3)
        ensure(health.get("status") == "ok" and health.get("environment") == "staging" and health.get("revision") == route["revision"], "Live baseline is not healthy")
    ensure(base.request("http://127.0.0.1:5175", "/version.json", timeout=3).get("revision") == route["revision"], "Live frontend revision differs")
    return {"route": route, "artifacts": copy.deepcopy(artifacts), "journal_path": str(journal_path)}


def restore_initial(rollout, initial, artifacts):
    rollout.ex.lost.clear()
    rollout.release_workflow_lock()
    rollout.ex.deadline = time.monotonic() + 180
    rollout.journal = rollout.load()
    rollout.journal.setdefault("slots", {})[initial["slot"]] = copy.deepcopy(artifacts)
    rollout.compose("up", "-d", "--no-build", f"api_{initial['slot']}", f"web_{initial['slot']}")
    rollout.wait_healthy(initial["slot"], artifacts["revision"])
    rollout.acquire_workflow_lock(initial["slot"])
    try:
        actual = rollout.route()
        if actual["slot"] != initial["slot"]:
            rollout.switch(initial["slot"], artifacts["revision"], actual["generation"] + 1, actual["slot"])
        current = rollout.route()
        rollout.fence_workflow_revision(artifacts["revision"])
        rollout.background(initial["slot"])
        rollout.finish(initial["slot"], artifacts["revision"], None, current["generation"])
        rollout.wait_healthy(initial["slot"], artifacts["revision"], public=True)
    finally:
        rollout.release_workflow_lock()
    return {"passed": True, "route": current, "initial_slot": initial["slot"], "same_revision": current["revision"] == initial["revision"]}


def run_acceptance(config, output, *, timeout=900):
    ensure(180 <= timeout <= 1800, "Timeout must be between 180 and 1800 seconds")
    identifier = uuid4().hex[:16]
    state = output.parent / ("bluegreen-recovery-" + identifier)
    state.mkdir(parents=True, exist_ok=False)
    report = {"scope": "isolated_real_docker_runtime_recovery", "passed": False, "started_at": time.time(),
        "excluded": ["source gates", "new revision build", "dataflow acceptance", "model calls", "upload authorization", "SSE/browser continuity"],
        "cases": {}, "state_directory": str(state), "production_modified": False}
    rollout = None
    initial = None
    try:
        baseline = live_snapshot(config)
        report["baseline"] = baseline
        ports = allocate_ports()
        project = PROJECT_PREFIX + identifier
        compose_file = state / "compose.json"
        bg.atomic_json(compose_file, isolated_spec(ports))
        env_file = state / "isolated.env"
        env_file.write_text("PLATFORM_DB_PASSWORD=" + uuid4().hex + "\nZHIYIN_AUTH_JWT_SECRET=" + uuid4().hex + uuid4().hex
            + "\nDASHSCOPE_API_KEY=isolated-no-model-calls\nZHIYIN_EXECUTOR_TOKEN=isolated-no-control-api\n", encoding="utf-8")
        local_config = {**config, "state_directory": str(state), "compose_file": str(compose_file), "bluegreen_compose_file": str(compose_file),
            "staging_env_file": str(env_file), "workbench_env_file": str(env_file), "acceptance_project": project,
            "acceptance_web": f"http://127.0.0.1:{ports['gateway_web']}", "acceptance_api": f"http://127.0.0.1:{ports['gateway_api']}",
            **{f"{slot}_{service}_port": ports[f"{slot}_{service}"] for slot in bg.SLOTS for service in ("api", "web")}}
        bg.atomic_json(state / "executor.json", local_config)
        artifacts = baseline["artifacts"]
        executor = AcceptanceExecutor(local_config, time.monotonic() + timeout, artifacts["revision"])
        executor.job = probe_job(artifacts["revision"])
        rollout = AcceptanceRollout(executor)
        for service in ("api", "web"):
            image = artifacts[f"{service}_image"]
            ensure(executor.run(["docker", "image", "inspect", "--format", "{{.Id}}", image]).strip() == image, "Accepted image is unavailable")
        slot = baseline["route"]["slot"]
        rollout.journal = {"schema": 1, "slots": {slot: artifacts}, "artifacts": {artifacts["revision"]: artifacts}, "successful": [artifacts["revision"]]}
        rollout.save()
        report.update(project=project, ports=ports)
        rollout.compose("up", "-d", "--no-build", f"api_{slot}", f"web_{slot}")
        rollout.wait_healthy(slot, artifacts["revision"])
        rollout.smoke(slot)
        rollout.acquire_workflow_lock(slot)
        try:
            rollout.switch(slot, artifacts["revision"], 1, None, start=True)
            rollout.fence_workflow_revision(artifacts["revision"])
            rollout.background(slot)
            rollout.finish(slot, artifacts["revision"], None, 1)
        finally:
            rollout.release_workflow_lock()
        initial = rollout.route()
        report["initial"] = initial
        for name, test in (("healthy_switch", successful_switch), ("bad_start_no_switch", bad_start),
                           ("post_switch_rollback", post_switch_failure), ("lease_restart_recovery", lease_recovery)):
            report["cases"][name] = {"passed": False, "started_at": time.time()}
            bg.atomic_json(output, report)
            report["cases"][name] = test(rollout, artifacts)
            ensure(report["cases"][name].get("passed") is True, f"{name}: {report['cases'][name].get('error', 'failed')}")
            report["cases"][name]["publication_after_case"] = publication_evidence(rollout, rollout.route()["slot"])
        report["passed"] = True
    except Exception as exc:  # noqa: BLE001 - Persist failure evidence and always restore the private stack.
        report["error"] = rollout.ex.redact(str(exc)) if rollout else str(exc)
    finally:
        if rollout:
            rollout.release_workflow_lock()
            try:
                if initial:
                    report["restored"] = restore_initial(rollout, initial, report["baseline"]["artifacts"])
            except Exception as exc:  # noqa: BLE001 - Cleanup failure must not hide the original evidence.
                report["passed"] = False
                report["restore_error"] = rollout.ex.redact(str(exc))
            try:
                rollout.ex.lost.clear()
                rollout.ex.deadline = time.monotonic() + 120
                rollout.compose("down", "--timeout", "5", "--remove-orphans", "--volumes")
                remaining = rollout.ex.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={rollout.project}"]).strip()
                ensure(not remaining, "Private acceptance containers remain after cleanup")
                report["cleaned_up"] = True
            except Exception as exc:  # noqa: BLE001 - Leave exact project name and recovery materials on failure.
                report["passed"] = False
                report["cleanup_error"] = rollout.ex.redact(str(exc))
            report["events"] = rollout.ex.events
        if "baseline" in report:
            try:
                report["baseline_after"] = live_snapshot(config)
                ensure(report["baseline_after"] == report["baseline"], "Live baseline changed during isolated acceptance")
                report["live_baseline_unchanged"] = True
            except Exception as exc:  # noqa: BLE001 - Baseline drift invalidates acceptance, never triggers live mutation.
                report["passed"] = False
                report["baseline_error"] = str(exc)
        report["finished_at"] = time.time()
        bg.atomic_json(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE.parent / ".platform/acceptance/bluegreen-recovery.json")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = run_acceptance(config, args.output.resolve(), timeout=args.timeout)
    print(json.dumps({"passed": report["passed"], "report": str(args.output.resolve()), "scope": report["scope"]}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
