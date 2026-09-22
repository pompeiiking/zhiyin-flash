"""架构守卫：把「代码依赖图不存在反向依赖或跨层直连」变成可执行断言。

验收项 1 原文：「代码依赖图不存在反向依赖或跨层直连」。

此前这条只能靠人工评审，因此出现了 `zhiyin-api` 直接 import 数据访问包的
`contracts.enums` 却无人发现的情况。本测试用 AST 静态解析所有源码的 import，
对照允许矩阵逐条校验，任何越层都会让 CI 直接失败。

本文件同时守卫三条硬规则：
1. 同一能力不得在两处定义（内核符号不得在别处重新定义）；
2. `zhiyin_kernel` 内不得 import 任何其它 zhiyin 包；
3. 包清单必须与 pyproject.toml 的发布单元一致（新增包不允许漏挂守卫）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]

PACKAGE_DIRS: dict[str, str] = {
    "zhiyin_kernel": "zhiyin-kernel",
    "zhiyin_api": "zhiyin-api",
    "zhiyin_business": "zhiyin-business",
    "zhiyin_orchestration": "zhiyin-orchestration",
    "zhiyin_data_sdk": "zhiyin-data-sdk",
    "zhiyin_infrastructure": "zhiyin-infrastructure",
    "zhiyin_boot": "zhiyin-boot",
}

ALL_PACKAGES = frozenset(PACKAGE_DIRS)

# 允许的依赖方向：
ALLOWED_DEPENDENCIES: dict[str, frozenset[str]] = {
    # 共享内核：零依赖，只放数据形状。
    "zhiyin_kernel": frozenset({"zhiyin_kernel"}),
    # BFF：业务 Port / Facade + 共享形状。数据访问契约一律不可见。
    # （原 business.published 发布面已删除：kernel 归位后它只是同义再导出，
    #   api 直接读 kernel 枚举与读模型即可，见 zhiyin_business/__init__.py 的说明。）
    "zhiyin_api": frozenset({"zhiyin_api", "zhiyin_business", "zhiyin_kernel"}),
    # 业务层面向编排层编程 + 共享形状 + SDK 契约。
    "zhiyin_business": frozenset(
        {"zhiyin_business", "zhiyin_orchestration", "zhiyin_data_sdk", "zhiyin_kernel"}
    ),
    # 编排层只依赖 SDK 与共享形状（R-ORC-008：不直连具体基础设施实现）。
    "zhiyin_orchestration": frozenset(
        {"zhiyin_orchestration", "zhiyin_data_sdk", "zhiyin_kernel"}
    ),
    # SDK 只定义契约（读写抽象 + 传输抽象），不承载领域模型。
    "zhiyin_data_sdk": frozenset({"zhiyin_data_sdk", "zhiyin_kernel"}),
    # 基础设施实现 SDK 契约（依赖倒置：方向是 infra → sdk）。
    "zhiyin_infrastructure": frozenset(
        {"zhiyin_infrastructure", "zhiyin_data_sdk", "zhiyin_kernel"}
    ),
    # 装配层是唯一允许 import 全部六层的地方。
    "zhiyin_boot": ALL_PACKAGES,
}

# 编排层不得出现的业务枚举（R-ORC-001：编排层不含业务语义）
BUSINESS_ONLY_SYMBOLS = (
    "LoopStage",
    "AgentRole",
    "AssetType",
    "BehaviorEventType",
    "ProfileSource",
    "ReviewAttribution",
    "PlanRole",
    "TaskStatus",
)


def _iter_sources(package: str):
    root = TEMPLATE_ROOT / PACKAGE_DIRS[package]
    return sorted(root.rglob("*.py"))


def _imported_roots(source: Path) -> set[str]:
    """收集一个文件里所有 zhiyin_* 的顶层包名。"""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in ALL_PACKAGES:
                    roots.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对 import 留在本包内
                continue
            if node.module:
                top = node.module.split(".")[0]
                if top in ALL_PACKAGES:
                    roots.add(top)
    return roots


@pytest.mark.parametrize("package", sorted(PACKAGE_DIRS))
def test_no_cross_layer_or_reverse_dependency(package: str) -> None:
    allowed = ALLOWED_DEPENDENCIES[package]
    violations: list[str] = []

    for source in _iter_sources(package):
        for root in _imported_roots(source):
            if root not in allowed:
                violations.append(
                    f"{source.relative_to(TEMPLATE_ROOT)} → {root}"
                )

    assert not violations, (
        f"{package} 出现越层/反向依赖：\n  "
        + "\n  ".join(violations)
    )


def test_api_does_not_touch_data_sdk() -> None:
    """单列一条：api 越层依赖 data-sdk 是本次修复的具体缺陷，别回退。"""
    offenders = []
    for source in _iter_sources("zhiyin_api"):
        if "zhiyin_data_sdk" in _imported_roots(source):
            offenders.append(source.relative_to(TEMPLATE_ROOT))
    assert not offenders, f"api 层不得直接依赖 data-sdk：{offenders}"


def test_business_actually_uses_orchestration() -> None:
    """反方向守卫：编排层不能是"没人引用的死层"。

    修复前全仓 0 处引用 zhiyin_orchestration，编排层只是金字塔上多画的一格。
    """
    users = [
        source.relative_to(TEMPLATE_ROOT)
        for source in _iter_sources("zhiyin_business")
        if "zhiyin_orchestration" in _imported_roots(source)
    ]
    assert users, "business 层必须真正使用编排层原语，否则编排层成为死层"


def test_orchestration_has_no_business_semantics() -> None:
    """R-ORC-001：编排层代码里不得出现业务枚举。"""
    offenders: list[str] = []
    for source in _iter_sources("zhiyin_orchestration"):
        text = source.read_text(encoding="utf-8")
        for symbol in BUSINESS_ONLY_SYMBOLS:
            if symbol in text:
                offenders.append(f"{source.relative_to(TEMPLATE_ROOT)}: {symbol}")
    assert not offenders, f"编排层出现业务语义，违反 R-ORC-001：{offenders}"


def test_infrastructure_never_imports_business() -> None:
    """基础设施层不得引用业务模型。

    修复前 persistence/models.py 的表清单写「key_calendar_node ← business/domain/function.CalendarNode」，
    心智模型已经反了；现在 CalendarNode 定义在 contracts，本测试守住这条线。
    """
    offenders = [
        source.relative_to(TEMPLATE_ROOT)
        for source in _iter_sources("zhiyin_infrastructure")
        if "zhiyin_business" in _imported_roots(source)
    ]
    assert not offenders, f"基础设施层不得引用业务层：{offenders}"


def test_kernel_has_no_dependencies() -> None:
    """硬规则 2：共享内核零依赖。

    内核一旦依赖别的 zhiyin 包，"所有层都能安全引用的最小内核"就不成立，
    依赖图会出现环路。这条守卫让首次违规就失败，而不是等分层评审发现。
    """
    offenders: list[str] = []
    for source in _iter_sources("zhiyin_kernel"):
        external = _imported_roots(source) - {"zhiyin_kernel"}
        if external:
            offenders.append(f"{source.relative_to(TEMPLATE_ROOT)} → {sorted(external)}")
    assert not offenders, f"共享内核不得依赖任何其它 zhiyin 包：{offenders}"


def test_kernel_holds_only_shapes_and_contracts() -> None:
    """内核只放两类东西：数据形状，和"零依赖的最小接口契约"。

    准入选自 `zhiyin_kernel/__init__.py` 的 docstring。这条守卫防的是内核慢慢变成
    杂物间：只要有人往内核的类里塞一个带方法体的方法（行为、IO、asyncio 循环），
    "所有层都能安全引用"的前提就没了——因为行为会带依赖，也会带副作用。

    允许：`@abstractmethod`（纯声明）、`@property`（无依赖的取值）。
    """
    offenders: list[str] = []
    for source in _iter_sources("zhiyin_kernel"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                decorators = {_decorator_name(d) for d in item.decorator_list}
                if decorators & {"abstractmethod", "property"}:
                    continue
                offenders.append(
                    f"{source.relative_to(TEMPLATE_ROOT)}::{node.name}.{item.name}"
                )
    assert not offenders, (
        "内核里出现了带方法体的方法（内核只允许数据形状与最小接口契约）：\n  "
        + "\n  ".join(offenders)
    )


def _decorator_name(node: ast.expr) -> str:
    """取装饰器名（`@abstractmethod` / `@property` / `@x.y` 统一取末段）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _defined_class_names(package: str) -> set[str]:
    """收集一个包里所有 class 定义名（用于查重复定义）。"""
    names: set[str] = set()
    for source in _iter_sources(package):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
    return names


def test_no_duplicate_contract_definitions() -> None:
    """硬规则 1：同一能力不得在两处定义。

    判定口径：内核导出的数据形状，不允许在其它包里再定义一次同名 class。
    影子定义（尤其在 SDK / 基础设施里重建一个同名字段集的类）比越层 import
    更难发现，也是"换实现要改两处"的根因。
    """
    from zhiyin_kernel import __all__ as kernel_exports

    kernel_symbols = set(kernel_exports)
    offenders: list[str] = []
    for package in sorted(PACKAGE_DIRS):
        if package == "zhiyin_kernel":
            continue
        duplicated = _defined_class_names(package) & kernel_symbols
        if duplicated:
            offenders.append(f"{package}: {sorted(duplicated)}")
    assert not offenders, f"内核符号被重复定义（应改为 import 内核）：{offenders}"


def test_package_list_matches_pyproject() -> None:
    """硬规则 3：新增包必须同时挂上守卫与发布单元。

    两步都容易漏：漏挂守卫则新包不受依赖矩阵约束；漏挂 pyproject 则
    `pip install -e .` 后 import 不到，只在别人机器上炸。
    """
    import tomllib

    pyproject = tomllib.loads(
        (TEMPLATE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = set(pyproject["tool"]["setuptools"]["packages"])
    missing = {
        f"{package}.{sub}"
        for package in PACKAGE_DIRS
        for sub in _submodule_names(package)
        if f"{package}.{sub}" not in declared
    }
    assert not missing, f"以下子包未登记在 pyproject.toml 的 packages：{sorted(missing)}"


def _submodule_names(package: str) -> list[str]:
    """列出包内一级子包目录名（不含 __pycache__）。"""
    root = TEMPLATE_ROOT / PACKAGE_DIRS[package] / package
    if not root.is_dir():
        return []
    return [
        item.name
        for item in root.iterdir()
        if item.is_dir()
        and not item.name.startswith("__")
        and item.name != "__pycache__"
        and (item / "__init__.py").is_file()
    ]


_BUSINESS_INTERNAL_RULES: dict[str, frozenset[str]] = {
    # ports 是契约层：不得依赖规则层或实现层。
    "ports": frozenset({"ports"}),
    # policies 是规则层：可以用 Port 与内核，不得依赖任何具体服务实现。
    "policies": frozenset({"policies", "ports"}),
}


@pytest.mark.parametrize("layer", sorted(_BUSINESS_INTERNAL_RULES))
def test_business_internal_direction(layer: str) -> None:
    """业务层内部方向：services → policies → ports → kernel，禁止倒流。

    这条守卫针对的是最容易发生的耦合：规则实现里 import 某个 Service 的
    方法，于是"规则改一处、服务动一串"。规则只能依赖 Port，才能被单测直接驱动。
    """
    root = TEMPLATE_ROOT / "zhiyin-business" / "zhiyin_business" / layer
    allowed = _BUSINESS_INTERNAL_RULES[layer]
    offenders: list[str] = []
    for source in sorted(root.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                if parts[:2] != ["zhiyin_business"] or len(parts) < 3:
                    continue
                inner = parts[2]
                if inner not in allowed:
                    offenders.append(
                        f"{source.relative_to(TEMPLATE_ROOT)} → zhiyin_business.{inner}"
                    )
    assert not offenders, (
        f"zhiyin_business/{layer}/ 出现反向依赖，违反 services → policies → ports："
        f"{offenders}"
    )
