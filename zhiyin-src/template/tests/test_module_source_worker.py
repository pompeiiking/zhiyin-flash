"""Real local Git tests for uploaded component composition; no Docker or network."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from uuid import uuid4
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = "zhiyin-src/template/zhiyin-modules/zhiyin_modules"


def git(directory, *args):
    result = subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip()


def sources(module_id="demo_module", version="1.0.0", *, marker="initial", **manifest_updates):
    manifest = {"id": module_id, "version": version, "reads": ["plan.read"], "actions": [], **manifest_updates}
    return {"manifest.json": json.dumps(manifest), "backend.py": f"MARKER = {marker!r}\n",
            "fixtures.json": "{}", "test_module.py": "def test_component():\n    assert True\n"}


def digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, value in entries:
            zipped.writestr(name, value)
    return stream.getvalue()


def write_module(directory, files, module_id="demo_module"):
    folder = directory / MODULE_ROOT / module_id
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (folder / name).write_text(value, encoding="utf-8")


def commit(directory, message):
    git(directory, "add", ".")
    git(directory, "-c", "commit.gpgsign=false", "commit", "-m", message)
    return git(directory, "rev-parse", "HEAD")


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "deploy"))
    spec = importlib.util.spec_from_file_location("tested_module_source_worker", ROOT / "deploy/module_source_worker.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def repository(tmp_path):
    directory = tmp_path / "controlled source"
    directory.mkdir()
    git(directory, "init", "--initial-branch=main")
    git(directory, "config", "user.name", "Source worker test")
    git(directory, "config", "user.email", "source-tests@local.invalid")
    git(directory, "config", "core.autocrlf", "false")
    (directory / "platform.txt").write_text("original platform", encoding="utf-8")
    write_module(directory, sources())
    return directory, commit(directory, "initial platform")


@pytest.fixture
def worker(module, repository, tmp_path):
    repo, base = repository
    environment = tmp_path / "isolated.env"
    environment.write_text("ZHIYIN_EXECUTOR_TOKEN=" + "t" * 40 + "\nPLATFORM_ACCOUNT_PASSWORD=test-password\n", encoding="utf-8")
    value = module.SourceWorker({"repository": str(repo), "state_directory": str(tmp_path / "worker-state"),
        "compose_file": str(tmp_path / "unused-compose.yml"), "staging_env_file": str(environment),
        "workbench_env_file": str(environment), "source_base_commit": base})
    value.recorded_updates = []
    value.parents = {}
    value.update = lambda **kwargs: value.recorded_updates.append(kwargs)
    value.api = lambda path, body=None: value.parents[path.removeprefix("/versions/")]
    return value


def version(base, files, **changes):
    return {"id": uuid4().hex, "lease": uuid4().hex, "project_id": "demo_module", "version": "2.0.0",
        "channel": "stable", "digest": digest(files), "base_commit": base, **changes}


@pytest.mark.parametrize("actual", ["", "f" * 40])
def test_unknown_installed_revision_blocks_before_checkout(worker, repository, actual):
    _, base = repository
    with pytest.raises(ValueError):
        worker.candidate(version(base, sources(version="2.0.0")), sources(version="2.0.0"), actual)
    assert not (worker.root / "sources").exists()


def test_old_installed_ancestor_does_not_erase_new_platform_baseline(worker, repository):
    repo, installed = repository
    (repo / "platform.txt").write_text("new upload and workflow support", encoding="utf-8")
    base = commit(repo, "new platform baseline")
    files = sources(version="2.0.0", marker="candidate")
    checkout, candidate = worker.candidate(version(base, files), files, installed)
    assert (checkout / "platform.txt").read_text(encoding="utf-8") == "new upload and workflow support"
    assert git(checkout, "rev-parse", "HEAD^") == base
    assert worker.report["effective_base_commit"] == base
    assert worker.report["expected_revision"] == installed
    assert worker.has_commit(candidate)


def test_other_developer_module_is_carried_forward_and_original_checkout_stays_dirty(worker, repository):
    repo, base = repository
    write_module(repo, sources("another_module", marker="already live"), "another_module")
    installed = commit(repo, "another developer already deployed")
    (repo / "uncommitted-note.txt").write_text("keep local changes", encoding="utf-8")
    original_status = git(repo, "status", "--short")
    files = sources(version="2.0.0", marker="new demo")
    checkout, candidate = worker.candidate(version(base, files), files, installed)
    assert git(checkout, "rev-parse", "HEAD^") == installed
    assert "already live" in (checkout / MODULE_ROOT / "another_module/backend.py").read_text(encoding="utf-8")
    changed = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", candidate).splitlines()
    assert changed and all(path.startswith(MODULE_ROOT + "/demo_module/") for path in changed)
    assert git(repo, "rev-parse", "HEAD") == installed
    assert git(repo, "status", "--short") == original_status
    assert worker.report["release_blockers"] == []


def test_same_module_new_release_without_explicit_base_version_is_rejected(worker, repository):
    repo, base = repository
    write_module(repo, sources(version="1.1.0", marker="already live"))
    installed = commit(repo, "same module changed")
    files = sources(version="2.0.0")
    with pytest.raises(ValueError, match="同一模块"):
        worker.candidate(version(base, files), files, installed)


def test_explicit_base_version_matching_current_module_allows_unrelated_later_changes(worker, repository):
    repo, base = repository
    write_module(repo, sources(version="1.1.0", marker="parent version"))
    parent = commit(repo, "module version 1.1")
    write_module(repo, sources("another_module", marker="later deployment"), "another_module")
    installed = commit(repo, "unrelated later module")
    worker.parents["parent-version"] = {"project_id": "demo_module", "candidate_commit": parent}
    files = sources(version="2.0.0")
    checkout, _ = worker.candidate(version(base, files, base_version_id="parent-version"), files, installed)
    assert git(checkout, "rev-parse", "HEAD^") == installed
    assert (checkout / MODULE_ROOT / "another_module/manifest.json").exists()


@pytest.mark.parametrize("case", ["stale_content", "wrong_project", "missing_commit"])
def test_explicit_base_cannot_authorize_overwriting_unmatched_module(worker, repository, case):
    repo, base = repository
    write_module(repo, sources(version="1.1.0", marker="parent version"))
    parent = commit(repo, "module version 1.1")
    write_module(repo, sources(version="1.2.0", marker="newer version"))
    installed = commit(repo, "module version 1.2")
    worker.parents["parent-version"] = {"project_id": "another_module" if case == "wrong_project" else "demo_module",
        "candidate_commit": "f" * 40 if case == "missing_commit" else parent}
    files = sources(version="2.0.0")
    with pytest.raises(ValueError, match="同一模块"):
        worker.candidate(version(base, files, base_version_id="parent-version"), files, installed)


def test_divergent_platform_baselines_require_explicit_merge(worker, repository):
    repo, common = repository
    (repo / "platform.txt").write_text("installed branch", encoding="utf-8")
    installed = commit(repo, "installed branch")
    git(repo, "checkout", "--detach", common)
    (repo / "platform.txt").write_text("other platform branch", encoding="utf-8")
    base = commit(repo, "diverged platform")
    files = sources(version="2.0.0")
    with pytest.raises(ValueError, match="分叉"):
        worker.candidate(version(base, files), files, installed)


@pytest.mark.parametrize("number", ["1.0.0", "0.9.0"])
def test_reused_or_decreasing_semantic_version_is_rejected(worker, repository, number):
    _, base = repository
    files = sources(version=number, marker="changed")
    with pytest.raises(ValueError, match="版本号必须高于"):
        worker.candidate(version(base, files, version=number), files, base)


def test_new_capability_and_schema_require_platform_compatibility_upgrade(worker, repository):
    _, base = repository
    files = sources(version="2.0.0", reads=["plan.read", "achievements.read"], output_schema={"type": "object"})
    worker.candidate(version(base, files), files, base)
    assert len(worker.report["release_blockers"]) == 2
    assert any("reads" in reason for reason in worker.report["release_blockers"])
    assert any("output_schema" in reason for reason in worker.report["release_blockers"])


@pytest.mark.parametrize("prefix", ["", "demo_module/"])
def test_package_digest_is_independent_of_optional_top_directory(module, prefix):
    files = sources()
    raw = archive([(prefix + name, value) for name, value in files.items()])
    assert module.package_sources(raw, "demo_module", digest(files)) == files
    with pytest.raises(ValueError, match="digest mismatch"):
        module.package_sources(raw, "demo_module", "0" * 64)


@pytest.mark.parametrize("unsafe", ["../backend.py", "demo_module/../backend.py", "/backend.py", "C:/backend.py",
    "demo_module\\..\\backend.py", "another_module/backend.py", "nested/backend.py", ".env", "conftest.py", "sitecustomize.py"])
def test_package_rejects_escape_paths_and_platform_execution_hooks(module, unsafe):
    raw = archive([(unsafe, "text")])
    with pytest.raises(ValueError, match="path|reserved"):
        module.package_sources(raw, "demo_module", digest({unsafe: "text"}))


def test_case_aliases_cannot_overwrite_files_on_windows(module):
    files = {"backend.py": "first", "Backend.py": "second"}
    with pytest.raises(ValueError, match="Duplicate"):
        module.package_sources(archive(files.items()), "demo_module", digest(files))


def test_zip_uncompressed_size_limit_applies_before_reading_sources(module):
    raw = archive([("backend.py", "x" * (8 * 1024 * 1024 + 1))])
    assert len(raw) < 2 * 1024 * 1024
    with pytest.raises(ValueError, match="limit"):
        module.package_sources(raw, "demo_module", "0" * 64)
