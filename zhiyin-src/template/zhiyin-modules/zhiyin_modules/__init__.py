"""Repository-installed modules, discovered from reviewed source at build/startup."""
from __future__ import annotations

import ast
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from functools import lru_cache
from jsonschema import Draft202012Validator, FormatChecker

from zhiyin_kernel.modules import ModuleManifest, ModuleResult

READS = frozenset({"plan.read", "achievements.read", "direction.read", "calendar.read"})
ACTIONS = frozenset({"plan.task.set_done"})
RESERVED_TOOLS = frozenset({"kb.search", "xuezhi.search", "web.search", "profile.read", "behavior.recent", "plan.read", "chart.render"})
RESERVED_MODULE_IDS = frozenset({"portrait", "talk", "todo", "collect", "plans", "action", "timetable", "calendar", "match", "market", "greet", "people", "review"})


@lru_cache(maxsize=256)
def _parse(source: str):
    # Inspect unchanged source once; changed source content gets a fresh tree.
    return ast.parse(source)


@dataclass(frozen=True)
class ModuleDefinition:
    manifest: ModuleManifest
    root: Path
    load: Callable
    validate: Callable

    def fixture(self, name: str = "normal") -> dict:
        return json.loads((self.root / "fixtures.json").read_text(encoding="utf-8"))[name]


def inspect_modules(root: Path | None = None) -> dict:
    root = root or Path(__file__).parent
    errors: list[dict] = []
    found: list[str] = []
    manifests: dict[str, ModuleManifest] = {}
    for path in sorted(root.glob("*/manifest.json")):
        try:
            m = ModuleManifest.model_validate_json(path.read_text(encoding="utf-8"))
            if m.tool and m.tool != f"{m.id}.read":
                raise ValueError("工具必须命名为 <模块编号>.read")
            if m.tool in RESERVED_TOOLS:
                raise ValueError("工具名称与平台内置工具重名")
            if m.id in RESERVED_MODULE_IDS:
                raise ValueError("模块编号与现有首页卡片重名")
            if m.id != path.parent.name or m.id in found:
                raise ValueError("目录与模块编号不一致，或编号重复")
            if set(m.reads) - READS or set(m.actions) - ACTIONS:
                raise ValueError("声明了平台未提供的数据能力或业务操作")
            for filename in {"backend.py", "fixtures.json", "test_module.py", m.card, m.detail, m.conversation, m.dataflow} - {None}:
                if not (path.parent / filename).is_file():
                    raise ValueError(f"缺少文件：{filename}")
            for source in path.parent.glob("*.py"):
                tree = _parse(source.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    names = ([x.name for x in node.names] if isinstance(node, ast.Import)
                             else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                    if any(n.split('.')[0] in {"os", "subprocess", "socket", "asyncpg", "httpx", "requests"}
                           or n.startswith("zhiyin_") and not n.startswith("zhiyin_kernel") for n in names):
                        raise ValueError(f"{source.name}:{node.lineno}：模块应通过上下文 SDK 访问平台")
            fixtures = json.loads((path.parent / "fixtures.json").read_text(encoding="utf-8"))
            if not {"normal", "empty", "error"}.issubset(fixtures):
                raise ValueError("缺少 normal/empty/error 示例场景")
            found.append(m.id)
            manifests[m.id] = m
        except Exception as exc:
            errors.append({"module": path.parent.name, "file": str(path.relative_to(root)), "message": str(exc)})
    for module_id, manifest in manifests.items():
        try:
            for dependency, version in manifest.dependencies.items():
                if dependency == module_id or dependency not in manifests:
                    raise ValueError(f"依赖模块不存在或依赖自身：{dependency}")
                if manifests[dependency].version != version:
                    raise ValueError(f"依赖版本不匹配：{dependency} 需要 {version}，当前为 {manifests[dependency].version}")
            pending = list(manifest.dependencies)
            checked = set()
            while pending:
                dependency = pending.pop()
                if dependency == module_id:
                    raise ValueError("模块依赖不能形成循环")
                if dependency not in checked and dependency in manifests:
                    checked.add(dependency)
                    pending.extend(manifests[dependency].dependencies)
            seen = {module_id}
            parent_id = manifest.parent_id
            while parent_id is not None:
                if parent_id in seen:
                    raise ValueError("模块层级不能引用自身或形成循环")
                seen.add(parent_id)
                if parent_id not in manifests:
                    raise ValueError(f"父模块不存在或未通过检查：{parent_id}")
                parent = manifests[parent_id]
                if parent.kind == "tool":
                    raise ValueError(f"父模块必须是应用或混合模块：{parent_id}")
                parent_id = parent.parent_id
        except ValueError as exc:
            errors.append({"module": module_id, "file": f"{module_id}/manifest.json", "message": str(exc)})
    return {"passed": not errors, "modules": found, "errors": errors}


def discover(root: Path | None = None) -> dict[str, ModuleDefinition]:
    root = root or Path(__file__).parent
    report = inspect_modules(root)
    if not report["passed"]:
        raise ValueError(json.dumps(report["errors"], ensure_ascii=False))
    result = {}
    for module_id in report["modules"]:
        folder = root / module_id
        manifest = ModuleManifest.model_validate_json((folder / "manifest.json").read_text(encoding="utf-8"))
        spec = importlib.util.spec_from_file_location(f"zhiyin_module_{module_id}", folder / "backend.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        definition = ModuleDefinition(manifest, folder, module.load, module.validate)
        # Output validators are mandatory even for empty fixture data.
        for fixture in ("normal", "empty"):
            data = definition.fixture(fixture)
            if "result" in data:
                value = ModuleResult.model_validate(module.validate(data["result"]))
                Draft202012Validator(manifest.output_schema, format_checker=FormatChecker()).validate(value.data)
        result[module_id] = definition
    return result
