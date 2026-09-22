"""依赖声明守卫：代码里 import 到的东西，必须写在 pyproject 的 dependencies 里。

为什么值得守
------------
同一份代码跑在两种环境里：

- **本机 / CI**：`pip install -e ".[dev]"`，而这台机器上早就装了一堆别的东西；
- **部署镜像**：`python:3.11-slim` + `pip install .`，里面**只有声明过的东西**。

于是"本机能 import"完全不能证明"镜像里也有"。本次实测到一次：镜像里服务起来就崩，
一直 Restarting，日志是

    ImportError: `openai` not installed. Please install using `pip install openai`

而本机、CI、全部单测都是绿的 —— 因为那三条都在同一个"碰巧装了 openai"
（别的项目 `document-agent` / `langchain-openai` 带进来的）的环境里跑。
这类缺陷**只在部署时出现**，靠人记得声明是不可靠的，所以在这里机械对账。

两件事：

1. 各包里的**直接 import** 逐个与 pyproject 的运行时依赖对账；
2. 对"别人的可选依赖"单列一条 —— agno 把模型后端做成 extra，
   `agno.models.openai` 依赖的 `openai` 分布不由 agno 自动带上，
   第 1 条按定义看不见它（我们没有直接 `import openai`）。
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = TEMPLATE_ROOT / "pyproject.toml"

#: 只扫代码包，不扫 tests / scripts：守卫管的是"跑起来需要什么"。
SKIPPED_PARTS = frozenset({"__pycache__", ".venv", "tests"})

#: 导入名不等于分布名的两个：`jwt` 来自 PyJWT；`starlette` 由 fastapi 硬依赖带上，
#: 我们不需要（也不该）单独把它列成自己的依赖。
IMPORT_NAME_ALIASES: dict[str, str] = {
    "jwt": "pyjwt",
    "starlette": "fastapi",
}


def _normalize(distribution: str) -> str:
    """分布名归一化：`PyJWT` → `pyjwt`，`pydantic-settings` → `pydantic_settings`。"""
    return distribution.strip().lower().replace("-", "_").replace(".", "_")


def _declared_runtime_dependencies() -> set[str]:
    """读 pyproject 的运行时依赖。

    刻意读**文件**而不是 `importlib.metadata.requires("zhiyin")`：后者反映的是
    "这台机器上一次装的是哪一版元数据"，本机上就出现过元数据比 pyproject 旧
    （少了 agno）的情况 —— 那样守卫会用一个过期的答案去判对错。
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared: set[str] = set()
    for spec in data["project"]["dependencies"]:
        # 只取分布名，丢掉版本区间与 marker：`fastapi>=0.110` → `fastapi`
        name = re.split(r"[<>=!~\[;\s]", spec.strip(), maxsplit=1)[0]
        declared.add(_normalize(name))
    return declared


def _runtime_imports() -> dict[str, list[str]]:
    """各代码包里出现的第三方顶层模块名 → 出现位置（用于报错时定位）。"""
    found: dict[str, list[str]] = {}
    for path in sorted(TEMPLATE_ROOT.glob("zhiyin-*/**/*.py")):
        if any(part in SKIPPED_PARTS for part in path.relative_to(TEMPLATE_ROOT).parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            else:
                continue
            for root in roots:
                found.setdefault(root, []).append(
                    str(path.relative_to(TEMPLATE_ROOT).as_posix())
                )
    return found


def test_every_imported_module_is_declared() -> None:
    """直接 import 的第三方模块必须在 pyproject 的 dependencies 里。"""
    declared = _declared_runtime_dependencies()
    undeclared: dict[str, list[str]] = {}

    for module, places in _runtime_imports().items():
        if module.startswith("zhiyin_") or module == "__future__":
            continue
        if module in sys.stdlib_module_names:
            continue
        if _normalize(module) in declared:
            continue
        if module in IMPORT_NAME_ALIASES:
            continue
        undeclared[module] = places

    assert not undeclared, (
        "以下第三方模块被 import 了，但没写进 pyproject 的 dependencies：\n  "
        + "\n  ".join(
            f"{module}（{sorted(set(places))[0]} 等 {len(places)} 处）"
            for module, places in sorted(undeclared.items())
        )
        + "\n本机装了不代表镜像里也有 —— 不声明就会在部署时才炸。"
    )


def test_agno_model_backend_dependency_is_declared() -> None:
    """agno 的模型后端是可选安装，我们用的那一个要自己声明。"""
    declared = _declared_runtime_dependencies()
    runtime = TEMPLATE_ROOT / "zhiyin-infrastructure/zhiyin_infrastructure/ai/agno_runtime.py"
    source = runtime.read_text(encoding="utf-8")
    assert "from agno.models.openai import" in source, (
        "agno 模型入口变了，请同步本守卫：它按 `agno.models.openai` 判定需要哪个后端分布"
    )
    assert "openai" in declared, (
        "代码用的是 `agno.models.openai.OpenAIChat`，而这个后端在 agno 里是**可选安装**："
        "`pip install agno` 不会带上 openai 分布。必须由本包声明 `openai`，"
        "否则部署镜像里 `import agno.models.openai` 直接 ImportError，容器起来就崩。"
    )
