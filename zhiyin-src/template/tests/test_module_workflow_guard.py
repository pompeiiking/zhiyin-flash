"""Published snapshot compatibility and real host subprocess lock lifecycle."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from tests.test_module_platform import platform as platform_fixture
from zhiyin_business.services.module_flows import ModuleFlowService


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("tested_workflow_guard", ROOT / "deploy/module_workflow_guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
A = "a" * 40


def snapshot(version="1.0.0", **changes):
    return {"id": "published_flow", "published_revision": 2,
        "definition": {"nodes": [{"id": "read_plan", "module_id": "action_progress", "module_version": version}], **changes}}


def test_guard_validates_real_service_without_running_business_data():
    platform = platform_fixture.__wrapped__()
    service = ModuleFlowService(platform, None)
    version = platform.modules["action_progress"].manifest.version
    passed = guard.validate_snapshots(service, [snapshot(version)])
    assert passed["passed"] is True
    rejected = guard.validate_snapshots(service, [snapshot("9.9.9"), {**snapshot(version), "id": "broken", "definition": None}])
    assert rejected["passed"] is False
    assert len(rejected["workflows"]) == 2
    first = rejected["workflows"][0]
    assert first["workflow_id"] == "published_flow"
    assert first["nodes"] == [{"node_id": "read_plan", "module_id": "action_progress", "module_version": "9.9.9"}]
    assert first["error"]
    assert guard.validate_snapshots(service, [])["passed"] is True


def test_guard_rejects_bad_bindings_even_when_all_versions_exist():
    platform = platform_fixture.__wrapped__()
    value = snapshot(platform.modules["action_progress"].manifest.version)
    value["definition"]["nodes"][0]["bindings"] = {"task_id": "absent/data/id"}
    report = guard.validate_snapshots(ModuleFlowService(platform, None), [value])
    assert report["passed"] is False and report["workflows"][0]["error"]


@pytest.fixture
def subprocess_guard(monkeypatch, tmp_path):
    """A real pipe process exercises host protocol without needing Docker/PG."""
    original = subprocess.Popen
    captured = []
    script = """
import json, sys
PREFIX = 'ZHIYIN_WORKFLOW_GUARD='
def emit(kind, **values):
    print(PREFIX + json.dumps({'type':kind, **values}), flush=True)
emit('READY', report={'passed':True,'workflows':[]})
for line in sys.stdin:
    message=json.loads(line)
    if message['operation']=='RELEASE': break
    if message['operation']=='PING': emit('PONG')
    if message['operation']=='FENCE': emit('FENCED',revision=message['revision'])
emit('RELEASED')
"""

    def launch(args, **kwargs):
        captured.append(args)
        return original([sys.executable, "-u", "-c", script], **kwargs)

    monkeypatch.setattr(guard.subprocess, "Popen", launch)
    executor = SimpleNamespace(lost=threading.Event())
    lock = guard.WorkflowPublicationGuard(executor, "b" * 64)
    yield lock, executor, captured
    lock.close()


def test_lock_subprocess_checks_report_fences_and_releases(subprocess_guard):
    lock, executor, calls = subprocess_guard
    assert lock.acquire() == {"passed": True, "workflows": []}
    lock.fence(A)
    lock.assert_alive()
    assert calls[0][:5] == ["docker", "exec", "-i", "b" * 64, "python"]
    assert "asyncio.run(container_main())" in calls[0][-1]
    lock.close()
    assert lock.process.poll() == 0
    with pytest.raises(RuntimeError, match="失效"):
        lock.assert_alive()


def test_lost_lease_aborts_and_releases_actual_child(subprocess_guard):
    lock, executor, _ = subprocess_guard
    lock.acquire()
    executor.lost.set()
    with pytest.raises(RuntimeError, match="失效"):
        lock.fence(A)
    lock.close()
    assert lock.process.poll() == 0


def test_failed_compatibility_closes_actual_helper_before_cutover(subprocess_guard, monkeypatch):
    lock, _, _ = subprocess_guard
    original = lock.receive

    def incompatible(kind, timeout):
        value = original(kind, timeout)
        value["report"] = {"passed": False, "workflows": [{"passed": False,
            "workflow_id": "published_flow", "nodes": [{"node_id": "read", "module_id": "progress", "module_version": "1.0.0"}],
            "error": "version mismatch"}]}
        return value

    monkeypatch.setattr(lock, "receive", incompatible)
    with pytest.raises(RuntimeError, match="published_flow.*progress.*1.0.0"):
        lock.acquire()
    assert lock.process.poll() == 0
    assert lock.report["passed"] is False


def test_guard_detects_dead_session_before_revision_update(subprocess_guard):
    lock, _, _ = subprocess_guard
    lock.acquire()
    lock.process.terminate()
    lock.process.wait(timeout=5)
    with pytest.raises(RuntimeError, match="失效"):
        lock.fence(A)


@pytest.mark.parametrize("identifier", ["", "api_green", "abc;cmd", "../container"])
def test_guard_never_accepts_arbitrary_container_command(identifier):
    with pytest.raises(ValueError):
        guard.WorkflowPublicationGuard(SimpleNamespace(), identifier)
