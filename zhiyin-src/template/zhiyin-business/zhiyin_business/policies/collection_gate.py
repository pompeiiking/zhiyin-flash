"""采集门槛：**采到什么时候算够了**。

为什么需要它
------------
以前"够不够"由模型自己在产出里写 `ready_to_handoff`，而那张写着门槛的表
（`policy_params.profile_collection`：关键字段覆盖 80%、整体把握 0.7）
**没有任何代码读**。后果就是真实用户遇到的那种：他只是想聊两句，
系统却一条接一条地问下去，问到人失去兴趣关掉页面。

所以门槛变成一条**可数的规则**：

    · 关键字段覆盖到多少（不知道你学什么、想去哪，后面每一步都算不准）
    · 整体把握到多少（有字段但全是"我猜的"，同样不够）

两个条件都满足才算够。阈值全部来自动态资源 —— 运营调它不需要发版，
而"一开始门槛松一点、让人先跑起来"正是最需要能调的那种参数。

小步快跑
--------
产品口径是**先让他跑起来，再慢慢磨合**：宁可带着一份不完整的画像进入下一环
（后面每一轮都会继续补），也不要为了"采全"把人在第一环耗走。
所以默认阈值刻意定得低，缺的那几条会以"缺口"的形式继续跟着他。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CollectionGate:
    """一次门槛判定的结果。"""

    ready: bool
    coverage: float
    overall: float
    missing: tuple[str, ...]

    @property
    def line(self) -> str:
        """给日志用的一句话。"""
        return (
            f"覆盖 {self.coverage:.0%} · 把握 {self.overall:.2f} · "
            f"{'够了' if self.ready else '还差 ' + '、'.join(self.missing)}"
        )


#: 策略读不到时的兜底：**要用一份具体的关键字段清单**，不能用空清单 ——
#: 空清单等于"一律算够"，那会让配置缺失直接表现成"跳过整个采集环节"。
#: 这份兜底只需要"比没有强"：够松（别卡住人），但不至于让人一步跨过采集。
_FALLBACK = {
    "key_fields": ("major", "interest", "target_direction"),
    "coverage_threshold": 0.5,
    "overall_confidence_threshold": 0.5,
    "gap_confidence_floor": 0.45,
}


def evaluate_gate(
    fields: Sequence[Any],
    policy: Mapping[str, Any] | None,
) -> CollectionGate:
    """按策略判一次"够了吗"。

    `fields` 是画像字段（`key` / `confidence`）。判定只用**已知事实**：
    字段在不在、把握多少 —— 不做语义推断。
    """
    merged = {**_FALLBACK, **(policy or {})}
    key_fields = tuple(str(item) for item in (merged.get("key_fields") or ()))
    coverage_threshold = float(merged.get("coverage_threshold") or 0.0)
    overall_threshold = float(merged.get("overall_confidence_threshold") or 0.0)
    floor = float(merged.get("gap_confidence_floor") or 0.0)

    by_key = {
        str(getattr(field, "key", "")): float(getattr(field, "confidence", 0.0) or 0.0)
        for field in fields
    }
    # "拿到了"的门槛比"覆盖"更低：一个字段只要把握过 floor 就算有了 ——
    # 要求每条都精确，等于逼着模型去猜（而它猜的那条会一直挂在画像上）。
    missing = tuple(key for key in key_fields if by_key.get(key, 0.0) < floor)
    coverage = 1.0 - len(missing) / len(key_fields)
    overall = (
        sum(by_key.values()) / len(by_key) if by_key else 0.0
    )
    ready = coverage >= coverage_threshold and overall >= overall_threshold
    return CollectionGate(ready=ready, coverage=coverage, overall=overall, missing=missing)


__all__ = ["CollectionGate", "evaluate_gate"]
