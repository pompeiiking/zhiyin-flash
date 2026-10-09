"""Uploaded source stays inert, scoped and immutable at the admission boundary."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import stat
from types import SimpleNamespace
import zipfile

import pytest

from zhiyin_business.services.developer import DeveloperPlatform
from zhiyin_business.services.module_packages import inspect_package
from zhiyin_kernel.developer import DeveloperProjectUpdate
from zhiyin_kernel.errors import AccessDenied, InvalidRequest


def sources():
    root = Path(__file__).resolve().parents[1] / "zhiyin-modules/zhiyin_modules/plan_progress_skill"
    return {p.name: p.read_text(encoding="utf-8") for p in root.iterdir() if p.is_file() and p.suffix in {".py", ".json"}}


def archive(files, prefix=""):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as package:
        for name, value in files.items():
            package.writestr(prefix + name, value)
    return base64.b64encode(data.getvalue()).decode()


def test_package_digest_ignores_zip_order_and_wrapper_directory():
    files = sources()
    first = inspect_package(archive(files), "plan_progress_skill")
    second = inspect_package(archive(dict(reversed(list(files.items()))), "plan_progress_skill/"), "plan_progress_skill")
    assert first[2:] == second[2:]


@pytest.mark.parametrize("filename", ["../outside.py", "/outside.py", "C:outside.py", "folder/inside.py", "x\\outside.py", "conftest.py", "sitecustomize.py", "usercustomize.py", ".env", "__init__.py", "Backend.py"])
def test_package_rejects_escape_bootstrap_and_case_collisions(filename):
    with pytest.raises(InvalidRequest):
        inspect_package(archive({**sources(), filename: "# no execution"}), "plan_progress_skill")


def test_package_checks_only_syntax_and_does_not_execute_upload():
    files = sources()
    files["backend.py"] = "raise RuntimeError('MUST NEVER EXECUTE AT UPLOAD')\n"
    assert inspect_package(archive(files), "plan_progress_skill")[1]["id"] == "plan_progress_skill"


def test_package_rejects_symlink():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as package:
        for name, value in sources().items():
            package.writestr(name, value)
        symlink = zipfile.ZipInfo("link.py")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(symlink, "../../outside.py")
    with pytest.raises(InvalidRequest, match="软链接"):
        inspect_package(base64.b64encode(data.getvalue()).decode(), "plan_progress_skill")


def test_package_rejects_duplicate_and_expansion_bomb():
    with pytest.raises(InvalidRequest):
        inspect_package(archive({**sources(), "large.py": " " * (1024 * 1024 + 1)}), "plan_progress_skill")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as package:
        for name, value in sources().items():
            package.writestr(name, value)
        with pytest.warns(UserWarning):
            package.writestr("backend.py", "# duplicate")
    with pytest.raises(InvalidRequest, match="重名"):
        inspect_package(base64.b64encode(data.getvalue()).decode(), "plan_progress_skill")


def test_identity_cannot_be_claimed_by_manifest():
    files = sources()
    manifest = json.loads(files["manifest.json"])
    manifest["id"] = "another_project"
    files["manifest.json"] = json.dumps(manifest)
    with pytest.raises(InvalidRequest, match="编号"):
        inspect_package(archive(files), "plan_progress_skill")


class Projects:
    async def project(self, project_id):
        return {"id": project_id, "owner": "owner", "members": ["member"], "trusted": True, "auto_deploy": False}


def user(name, role="developer"):
    return SimpleNamespace(id=name, role=SimpleNamespace(value=role))


@pytest.mark.asyncio
async def test_member_can_upload_but_not_manage_or_grant_trust():
    service = DeveloperPlatform(None, Projects(), None, None)
    assert (await service.project("module", user("member")))["id"] == "module"
    with pytest.raises(AccessDenied):
        await service.project("module", user("member"), manage=True)
    with pytest.raises(AccessDenied):
        await service.project("module", user("stranger"))
    with pytest.raises(AccessDenied, match="管理员"):
        await service.configure("module", DeveloperProjectUpdate(revision=1, name="Test", trusted=True, auto_deploy=True), user("owner"))
    assert await service.project("module", user("administrator", "admin"), manage=True)
