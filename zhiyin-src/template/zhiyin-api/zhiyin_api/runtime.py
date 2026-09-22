"""运行时装配状态（只读）。

为什么放在 api 层：`/healthz` 需要回答"哪些部件真的装上了、哪些还是骨架"，
但 api 不允许 import `zhiyin-boot`（会构成反向依赖）。因此约定：

- `zhiyin-boot` 在 wire 阶段构造一份 `AssemblyReport` 并调用 `configure_runtime()`；
- api 只读这份报告，不认识 boot 的任何类型。

这样「骨架隔离」变得可观测：healthz 会列出所有仍走本地/默认通过
实现的部件，以及第一期已知的功能缺口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# 部件状态取值
WIRED = "wired"
SKELETON = "skeleton"
NOT_WIRED = "not_wired"


@dataclass
class AssemblyReport:
    """一次启动的装配快照。

    分组与装配清单（`zhiyin_boot.container.ports`）一一对应：
    Gateways / Repositories / Orchestration / Services / Workers。
    """

    env: str = "local"
    gateways: dict[str, str] = field(default_factory=dict)
    repositories: dict[str, str] = field(default_factory=dict)
    orchestration: dict[str, str] = field(default_factory=dict)
    services: dict[str, str] = field(default_factory=dict)
    workers: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    skeletons: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        """没有任何部件处于 not_wired 才算健康。

        注意：`healthy` **不**把 skeleton 算作不健康（第一期允许骨架存在，门禁按
        里程碑分级判断）。"骨架有多少、分别属于谁"看 `skeletons`——它回答的是
        "外壳铺好了但能力还没接"，与 not_wired 的"外壳都没有"是两件事。
        """
        groups = (
            self.gateways,
            self.repositories,
            self.orchestration,
            self.services,
            self.workers,
        )
        if not any(groups):
            # 空报告（裸 create_app，或 boot 传了一份什么都没装进去的报告）不是"健康"。
            # 此前这里对空字典做 `NOT_WIRED in {}` 必然为 False，于是"什么都没装配"
            # 会被报成 healthy: true —— 恰好是装配报告最不该撒的那个谎。
            return False
        return not any(NOT_WIRED in group.values() for group in groups)

    def to_dict(self) -> dict:
        return {
            "env": self.env,
            "healthy": self.healthy,
            "gateways": dict(self.gateways),
            "repositories": dict(self.repositories),
            "orchestration": dict(self.orchestration),
            "services": dict(self.services),
            "workers": dict(self.workers),
            "missing": list(self.missing),
            "skeletons": list(self.skeletons),
        }


_report: Optional[AssemblyReport] = None

#: 读缓存自述探针：由 boot 在装配时注册成 `container.read_cache.stats`。
#:
#: 单独一条通道（而不是塞进 AssemblyReport）是因为装配报告是**一次启动的快照**，
#: 而缓存命中率是**持续变化**的运行时计数 —— 探针每次请求现取，报告保持不变。
_cache_probe: Optional[Callable[[], dict[str, Any]]] = None


def configure_runtime(report: AssemblyReport) -> None:
    """由 zhiyin-boot 在启动时调用。"""
    global _report
    _report = report


def configure_cache_probe(probe: Optional[Callable[[], dict[str, Any]]]) -> None:
    """由 zhiyin-boot 在装配时注册读缓存自述探针（未装配读缓存时传 None）。"""
    global _cache_probe
    _cache_probe = probe


def cache_snapshot() -> dict[str, Any]:
    """现取读缓存自述；没有读缓存（或探针抛错）时返回空字典，探针本身不影响健康判定。"""
    if _cache_probe is None:
        return {}
    try:
        return _cache_probe()
    except Exception:  # noqa: BLE001 - 自述失败不该让 /healthz 变成 500
        return {}


def get_runtime() -> AssemblyReport:
    """读取装配报告。未装配时返回空报告，healthz 仍可用。"""
    return _report if _report is not None else AssemblyReport()


def reset_runtime() -> None:
    """清空装配报告。供测试隔离使用，业务代码不应调用。"""
    global _report, _cache_probe
    _report = None
    _cache_probe = None
