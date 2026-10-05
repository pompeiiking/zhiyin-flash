"""Decode module source packages without importing or executing any uploaded code."""
from __future__ import annotations

import ast
import base64
import binascii
import hashlib
import io
import json
import re
import stat
import zipfile

from zhiyin_kernel.errors import InvalidRequest
from zhiyin_kernel.modules import ModuleManifest

MAX_COMPRESSED = 2 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
MAX_FILES = 100


def inspect_package(encoded: str, project_id: str) -> tuple[bytes, dict, str, dict[str, str]]:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidRequest("模块包必须是有效的 Base64 ZIP") from exc
    if len(raw) > MAX_COMPRESSED:
        raise InvalidRequest("ZIP 大小不能超过 2 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_FILES:
                raise InvalidRequest("模块包须包含 1 到 100 个文件")
            if sum(item.file_size for item in entries) > MAX_EXPANDED:
                raise InvalidRequest("解压后总大小不能超过 8 MiB")
            files: dict[str, str] = {}
            normalized: set[str] = set()
            for item in entries:
                name = item.filename
                if "\\" in name or name.startswith("/") or ":" in name or "\x00" in name:
                    raise InvalidRequest(f"不允许的包路径：{name}")
                if stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                    raise InvalidRequest("不允许软链接或加密文件")
                parts = name.rstrip("/").split("/")
                if parts[0] == project_id and len(parts) > 1:
                    parts = parts[1:]
                if item.is_dir() and name == project_id + "/":
                    continue
                if len(parts) != 1 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*\.(py|json|vue)", parts[0]):
                    raise InvalidRequest(f"模块仅支持平铺的 Python、JSON、Vue 源码：{name}")
                name = parts[0]
                if name.lower() in {"conftest.py", "sitecustomize.py", "usercustomize.py"}:
                    raise InvalidRequest(f"不允许覆盖平台执行入口：{name}")
                if name.casefold() in normalized:
                    raise InvalidRequest(f"文件重名或大小写冲突：{name}")
                normalized.add(name.casefold())
                if item.file_size > 1024 * 1024:
                    raise InvalidRequest(f"单文件超过 1 MiB：{name}")
                content = archive.read(item)
                if len(content) != item.file_size:
                    raise InvalidRequest("ZIP 文件长度不一致")
                files[name] = content.decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, OSError) as exc:
        raise InvalidRequest("模块包损坏或源码不是 UTF-8") from exc
    required = {"manifest.json", "backend.py", "fixtures.json", "test_module.py"}
    if required - files.keys():
        raise InvalidRequest("缺少模块文件：" + ", ".join(sorted(required - files.keys())))
    try:
        manifest = ModuleManifest.model_validate_json(files["manifest.json"])
        if manifest.id != project_id:
            raise InvalidRequest("清单编号必须与项目编号一致")
        for component in {manifest.card, manifest.detail, manifest.conversation} - {None}:
            if component not in files:
                raise InvalidRequest(f"缺少声明的组件：{component}")
        fixtures = json.loads(files["fixtures.json"])
        if not isinstance(fixtures, dict) or not {"normal", "empty", "error"}.issubset(fixtures):
            raise InvalidRequest("须提供 normal、empty、error 三个验收场景")
        for name, content in files.items():
            if name.endswith(".py"):
                ast.parse(content, filename=name)
    except (ValueError, SyntaxError) as exc:
        raise InvalidRequest(f"模块声明或源码格式错误：{exc}") from exc
    # Hash canonical source, so ZIP ordering and timestamps do not create different versions.
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return raw, manifest.model_dump(), digest, files
