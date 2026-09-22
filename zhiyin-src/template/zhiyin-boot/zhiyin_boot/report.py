"""装配报告与分级门禁。

设计原则（来自评估结论的具体缺陷）：

1. **状态由实现自己声明**：适配器类上的 `IMPLEMENTATION_STATUS`（wired / skeleton）
   优先，其次才回落到"本地实现目录"的路径启发式。
   这样 `/healthz` 不会因为"文件放对目录了"就谎报 wired。
2. **缺口带归属**：负责人清单读 `data/registry/ownership.json`，不再硬编码在
   Python 里（此前 `_KNOWN_PENDING` 把团队信息写进了装配代码）。
3. **门禁分级**：门禁定义读 `data/registry/assembly_gates.json`，支持
   `--check --phase=N`。二值的 healthy 只有一个含义（"全绿"），无法表达
   "框架已就绪但业务未接"，分级门禁让 CI 能按里程碑精确卡口。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from zhiyin_boot.container.ports import (
    GATEWAY_PORTS,
    ORCHESTRATION_PORTS,
    REPOSITORY_PORTS,
    SERVICE_PORTS,
    WORKER_PORTS,
)

if TYPE_CHECKING:  # pragma: no cover
    from zhiyin_api.runtime import AssemblyReport
    from zhiyin_boot.container import Container

from zhiyin_boot import runtime_config

DEFAULT_OWNER = "待认领"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_ownership(registry_dir: str) -> dict[str, str]:
    """读取能力位 → 负责人映射。

    优先用**启动时从 `infra_runtime_config` 读到的那份**（键 `assembly.ownership`）；
    库里没有才退回读文件。文件只是首次种子 —— 换一台机器只搬数据库，
    不该还要把 JSON 一起带过去。
    """
    raw = runtime_config.get(runtime_config.OWNERSHIP_KEY)
    if raw is None:
        raw = _read_json(Path(registry_dir) / "ownership.json")
    if not isinstance(raw, dict):
        return {}
    items = raw.get("items")
    if not isinstance(items, list):
        return {}
    owners: dict[str, str] = {}
    for item in items:
        if isinstance(item, dict) and item.get("port"):
            owners[str(item["port"])] = str(item.get("owner") or DEFAULT_OWNER)
    return owners


def _status_of(value: Any, *, skeleton_markers: tuple[str, ...]) -> str:
    """判断一个已装配部件的状态：实现自述优先，路径启发式兜底。"""
    from zhiyin_api.runtime import SKELETON, WIRED

    if value is None:
        from zhiyin_api.runtime import NOT_WIRED

        return NOT_WIRED
    declared = getattr(type(value), "IMPLEMENTATION_STATUS", None)
    if declared in {WIRED, SKELETON}:
        return declared
    module = type(value).__module__
    return SKELETON if any(marker in module for marker in skeleton_markers) else WIRED


def describe_assembly(container: "Container") -> "AssemblyReport":
    """生成装配报告，供 `/healthz` 与 `--check` 使用。"""
    from zhiyin_api.runtime import WIRED, AssemblyReport

    report = AssemblyReport(env=container.settings.env)
    registry_dir = container.settings.local_registry_dir

    for name in GATEWAY_PORTS:
        report.gateways[name] = _status_of(
            getattr(container, name, None), skeleton_markers=()
        )

    for name in REPOSITORY_PORTS:
        report.repositories[name] = _status_of(
            getattr(container, name, None), skeleton_markers=(".persistence.",)
        )

    for name in ORCHESTRATION_PORTS:
        report.orchestration[name] = (
            WIRED if getattr(container, name, None) is not None else "not_wired"
        )

    # 服务与 Worker 也读实现自述：骨架（IMPLEMENTATION_STATUS="skeleton"）必须被
    # 标成 skeleton，否则"类骨架已就位"会被误读成"能力已具备"——这正是本期大规模
    # 铺设骨架之后最容易发生的假装配。无骨架标记的既有实现仍报 wired。
    for name in SERVICE_PORTS:
        report.services[name] = _status_of(
            getattr(container, name, None), skeleton_markers=()
        )

    registered = {
        getattr(worker, "name", ""): worker
        for worker in getattr(container, "workers", []) or []
    }
    for name in WORKER_PORTS:
        report.workers[name] = _status_of(
            registered.get(name), skeleton_markers=()
        )

    ownership = load_ownership(registry_dir)
    report.missing = _collect_missing(report, ownership)
    report.skeletons = _collect_skeletons(report, ownership)
    return report


def _collect_skeletons(
    report: "AssemblyReport", ownership: Mapping[str, str]
) -> list[str]:
    """列出"已装配但仍是骨架"的部件（如铺好签名但未写实现的业务服务）。

    与 `missing`（未装配）分开，因为两者要回答的问题不同：
    `missing` 是"这个能力位没人管"，`skeletons` 是"外壳就位、实现待补"。
    本期大规模铺骨架之后，后者才是进度主视图。
    """
    from zhiyin_api.runtime import SKELETON

    skeletons: list[str] = []
    groups = {
        "gateways": report.gateways,
        "repositories": report.repositories,
        "orchestration": report.orchestration,
        "services": report.services,
        "workers": report.workers,
    }
    for group_name, group in groups.items():
        for port, status in group.items():
            if status == SKELETON:
                owner = ownership.get(port, DEFAULT_OWNER)
                skeletons.append(f"{group_name}.{port}：骨架，待 {owner} 补实现")
    return skeletons


def _collect_missing(
    report: "AssemblyReport", ownership: Mapping[str, str]
) -> list[str]:
    """列出未装配的部件与归属，供 `--check` 与 `/healthz` 直接展示。"""
    from zhiyin_api.runtime import NOT_WIRED

    missing: list[str] = []
    groups = {
        "gateways": report.gateways,
        "repositories": report.repositories,
        "orchestration": report.orchestration,
        "services": report.services,
        "workers": report.workers,
    }
    for group_name, group in groups.items():
        for port, status in group.items():
            if status == NOT_WIRED:
                owner = ownership.get(port, DEFAULT_OWNER)
                missing.append(f"{group_name}.{port}：待 {owner}")
    return missing


# --------------------------------------------------------------------------
# 分级门禁
# --------------------------------------------------------------------------


@dataclass
class PhaseGate:
    """一个里程碑的退出条件。"""

    phase: int
    name: str
    description: str = ""
    require: dict[str, list[str]] = field(default_factory=dict)
    allow_skeleton: bool = True
    manual: list[str] = field(default_factory=list)


@dataclass
class GateResult:
    """门禁判定结果。"""

    gate: PhaseGate
    unmet: list[str] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unmet

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.gate.phase,
            "name": self.gate.name,
            "passed": self.passed,
            "unmet": list(self.unmet),
            "manual": list(self.manual),
        }


def load_gates(registry_dir: str) -> list[PhaseGate]:
    """读取门禁定义（与归属同一口径：库优先，文件兜底）。"""
    raw = runtime_config.get(runtime_config.GATES_KEY)
    if raw is None:
        raw = _read_json(Path(registry_dir) / "assembly_gates.json")
    if not isinstance(raw, dict):
        return []
    items = raw.get("items")
    if not isinstance(items, list):
        return []
    gates: list[PhaseGate] = []
    for item in items:
        if not isinstance(item, dict) or "phase" not in item:
            continue
        gates.append(
            PhaseGate(
                phase=int(item["phase"]),
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                require={
                    str(group): [str(port) for port in ports]
                    for group, ports in (item.get("require") or {}).items()
                },
                allow_skeleton=bool(item.get("allow_skeleton", True)),
                manual=[str(text) for text in item.get("manual", []) or []],
            )
        )
    gates.sort(key=lambda gate: gate.phase)
    return gates


def evaluate_gate(report: "AssemblyReport", gate: PhaseGate) -> GateResult:
    """判定报告是否满足一个里程碑的退出条件。"""
    from zhiyin_api.runtime import SKELETON, WIRED

    groups: dict[str, Mapping[str, str]] = {
        "gateways": report.gateways,
        "repositories": report.repositories,
        "orchestration": report.orchestration,
        "services": report.services,
        "workers": report.workers,
    }
    unmet: list[str] = []
    for group_name, ports in gate.require.items():
        group = groups.get(group_name)
        if group is None:
            unmet.append(f"{group_name}：门禁引用了未知分组")
            continue
        for port in ports:
            status = group.get(port)
            if status is None:
                unmet.append(f"{group_name}.{port}：门禁引用了未登记的能力位")
            elif status != WIRED and not (gate.allow_skeleton and status == SKELETON):
                unmet.append(f"{group_name}.{port}={status}")
    return GateResult(gate=gate, unmet=unmet, manual=list(gate.manual))


__all__ = [
    "DEFAULT_OWNER",
    "GateResult",
    "PhaseGate",
    "describe_assembly",
    "evaluate_gate",
    "load_gates",
    "load_ownership",
]
