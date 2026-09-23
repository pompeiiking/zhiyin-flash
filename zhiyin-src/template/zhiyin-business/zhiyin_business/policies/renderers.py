"""可视件的白名单与校验：**模型只能挑类别，数据由服务端填**。

这一层是"自己做的功能模块"能被安全接进来的门。

一个模块要落地，是三件事：

1. **后端取数**（模块自己的逻辑，例如从库里读、或走某个数据源）；
2. **注册一种可视件**（这里 `register_renderer`：给它一个 kind 名与一个校验函数）；
3. **前端写一个组件**（按 kind 分发，渲染 `payload`）。

模型那一侧只需要一个工具：它挑 kind + 给检索词，**没有位置传数值** ——
点位由 1 算出来，形状由 2 把关，长什么样由 3 决定。

为什么校验必须在这里、而不是在工具里：
工具是模型能调用的入口，它的实现以后会被改；而**用户看不出哪个点是编的**。
所以在"要发给用户"的边界上再验一次：不认识的 kind 直接拒绝，
认识的 kind 交给它自己的校验函数（形状不对就整件丢掉），并留日志。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from zhiyin_business.contracts.common import Renderable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RendererSpec:
    """一种可视件：它叫什么、数据从哪来、怎么校验。"""

    kind: str
    #: 给人看的名字（写进日志与文档；不直接给用户看）
    label: str
    #: 数据来源的一句话说明（"画像里的把握度"/"学职平台公开页面"…）
    source: str
    #: payload → 规范化后的 payload；抛异常表示这件数据不合规
    validate: Callable[[dict[str, Any]], dict[str, Any]]


_RENDERERS: dict[str, RendererSpec] = {}


def register_renderer(spec: RendererSpec) -> None:
    """注册一种可视件。同名重复注册**直接抛** —— 那是两个模块抢一个 kind。"""
    if spec.kind in _RENDERERS:
        raise ValueError(f"可视件类型重复注册：{spec.kind}")
    _RENDERERS[spec.kind] = spec


def renderer_for(kind: str) -> RendererSpec | None:
    return _RENDERERS.get(kind)


def known_kinds() -> list[str]:
    """已注册的 kind（给工具与文档用：模型该看到一份真实清单）。"""
    return sorted(_RENDERERS)


def validate_renderables(raw: Any) -> list[Renderable]:
    """把工具产出的一批可视件逐个验一遍，不合规的**丢掉并留日志**。

    输入是原始数据（可能是工具写进回传盒子的任何东西），输出一定是可以直接
    发给用户的可视件 —— 宁可少给一件，也不给一件说不清的。
    """
    if not isinstance(raw, list):
        return []
    kept: list[Renderable] = []
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("可视件不是对象，已丢弃：%s", str(item)[:120])
            continue
        kind = str(item.get("kind") or "")
        spec = renderer_for(kind)
        if spec is None:
            logger.warning("可视件类型没注册过，已丢弃：%s（已知：%s）", kind, known_kinds())
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            logger.warning("可视件 %s 的 payload 不是对象，已丢弃", kind)
            continue
        try:
            checked = spec.validate(payload)
        except Exception as exc:  # noqa: BLE001 - 模块自己的校验，抛了就是不合规
            logger.warning("可视件 %s 没通过校验，已丢弃：%s", kind, exc)
            continue
        kept.append(
            Renderable(
                kind=kind,
                title=str(item.get("title") or "")[:40],
                payload=checked,
                source_refs=list(item.get("source_refs") or [])[:4],
            )
        )
    return kept


def _validate_bars(payload: dict[str, Any]) -> dict[str, Any]:
    """柱状图：至少两个点、每个点有名字与数值。"""
    points = payload.get("points")
    if not isinstance(points, list):
        raise ValueError("points 必须是数组")
    checked: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("每个点必须是对象")
        label = str(point.get("label") or "").strip()
        if not label:
            raise ValueError("有点没有名字")
        try:
            value = float(point.get("value"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} 的数值读不出来") from exc
        checked.append({"label": label[:12], "value": value})
    if len(checked) < 2:
        raise ValueError("一个点画不成图")
    return {
        "unit": str(payload.get("unit") or "")[:4],
        "points": checked,
    }


#: 第一种可视件：柱状图。点位一律由服务端从库里读（画像把握度 / 方案匹配度 / 计划进度）。
register_renderer(
    RendererSpec(
        kind="bars_chart",
        label="柱状图",
        source="画像把握度 / 已存方案分值 / 已存计划完成情况（都在库里）",
        validate=_validate_bars,
    )
)


__all__ = [
    "RendererSpec",
    "known_kinds",
    "register_renderer",
    "renderer_for",
    "validate_renderables",
]
