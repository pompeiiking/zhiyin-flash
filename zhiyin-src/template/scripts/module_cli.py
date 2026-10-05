"""Create a complete module from the runnable template, or check repository modules."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from zhiyin_kernel.modules import ModuleManifest
from zhiyin_modules import inspect_modules

ROOT = Path(__file__).resolve().parents[1] / "zhiyin-modules" / "zhiyin_modules"


def create(module_id: str, name: str, owner: str, kind: str = "hybrid", parent: str | None = None):
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", module_id):
        raise ValueError("模块编号必须由小写字母、数字和下划线组成，以字母开头")
    if kind not in {"application", "tool", "hybrid"}:
        raise ValueError("模块类型必须是 application、tool 或 hybrid")
    if parent:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", parent) or parent == module_id:
            raise ValueError("父模块编号不合法，或与当前模块相同")
        parent_file = ROOT / parent / "manifest.json"
        if not parent_file.is_file():
            raise ValueError("父模块不存在，请先创建父应用模块")
        parent_manifest = ModuleManifest.model_validate_json(parent_file.read_text(encoding="utf-8"))
        if parent_manifest.kind == "tool":
            raise ValueError("技能组件不能作为父模块")
    destination = ROOT / module_id
    if destination.exists():
        raise ValueError("模块目录已存在，拒绝覆盖")
    source = ROOT / ("plan_progress_skill" if kind == "tool" else "action_progress")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(id=module_id, name=name, owner=owner, kind=kind, parent_id=parent,
                    tool=None if kind == "application" else f"{module_id}.read")
    manifest.update(input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object", "required": ["total", "completed", "tasks"], "properties": {
            "total": {"type": "integer", "minimum": 0}, "completed": {"type": "integer", "minimum": 0},
            "tasks": {"type": "array", "items": {"type": "object"}}}}, dependencies={}, dataflow="dataflow.json")
    if kind == "application":
        manifest["conversation"] = None
    elif kind == "tool":
        manifest.update(card=None, detail=None, conversation=None, actions=[],
                        description="只读查询已保存的行动计划及任务进度，返回结构化数据供智能体使用。")
    # Validate before copying so a rejected declaration does not leave a partial module.
    ModuleManifest.model_validate(manifest)
    ignored = ["__pycache__", "*.pyc"] + (["*.vue"] if kind == "tool" else [])
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*ignored))
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dataflow = {"input": {}, "fixture_assertions": [
        {"fixture": "normal", "path": "/data/total", "equals": 2},
        {"fixture": "empty", "path": "/empty", "equals": True}],
        "live_assertions": [{"path": "/data/total", "equals": 2}]}
    (destination / "dataflow.json").write_text(json.dumps(dataflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {destination}; new modules start disabled until an administrator grants capabilities.")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    new = commands.add_parser("new")
    new.add_argument("id")
    new.add_argument("--name", required=True)
    new.add_argument("--owner", required=True)
    new.add_argument("--kind", choices=("application", "tool", "hybrid"), default="hybrid",
                     help="application: 用户功能；tool: 智能体技能；hybrid: 用户功能兼智能体工具")
    new.add_argument("--parent", help="所属父应用模块编号；技能组件不能作为父模块")
    args = parser.parse_args()
    if args.command == "new":
        create(args.id, args.name, args.owner, args.kind, args.parent)
    else:
        report = inspect_modules()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["passed"] else 1)
