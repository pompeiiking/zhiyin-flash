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

第三件事：**这条值由谁出具**
--------------------------
"关键字段覆盖"曾经只数"键在不在画像里、把握够不够"。于是用户在对话里随口说的
一句"计算机大类"就把 `major` 顶成了"已覆盖"，门槛跟着放行 —— 他带着一条**没人核验过**
的学籍离开 ①，学信网核验这一步再也不会有人提。所以覆盖现在与采集清单共用同一个判定
（`policies/collection.py::counts_as_got`）：权威字段要来源相称才算拿到，
非权威字段口径一个字没变。

小步快跑
--------
产品口径是**先让他跑起来，再慢慢磨合**：宁可带着一份不完整的画像进入下一环
（后面每一轮都会继续补），也不要为了"采全"把人在第一环耗走。
所以默认阈值刻意定得低，缺的那几条会以"缺口"的形式继续跟着他。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from zhiyin_business.policies.collection import counts_as_got


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
    *,
    rules: Sequence[Any] | None = None,
) -> CollectionGate:
    """按策略判一次"够了吗"。

    `fields` 是画像字段（`key` / `confidence` / `source`）。判定只用**已知事实**：
    字段在不在、把握多少、以及**这条值由谁出具** —— 不做语义推断。

    `rules` 是采集登记表（`collection_rules.json`，读法见 `plan_collection`）：
    "哪个字段该由谁出具"写在它里面。不传时退回 `policies/collection.py` 的内置表。

    **阈值一个都没动**：`coverage >= coverage_threshold and overall >= overall_threshold`
    仍是原样，两个参数仍来自动态资源。来源相称这一维只改"这个数字算得对不对"。
    """
    merged = {**_FALLBACK, **(policy or {})}
    key_fields = tuple(str(item) for item in (merged.get("key_fields") or ()))
    coverage_threshold = float(merged.get("coverage_threshold") or 0.0)
    overall_threshold = float(merged.get("overall_confidence_threshold") or 0.0)
    floor = float(merged.get("gap_confidence_floor") or 0.0)

    by_key = {str(getattr(field, "key", "")): field for field in fields}

    def got(key: str) -> bool:
        field = by_key.get(key)
        if field is None:
            return False
        # 把握度这一维保持原样：一个字段只要把握过 floor 就算有了 ——
        # 要求每条都精确，等于逼着模型去猜（而它猜的那条会一直挂在画像上）。
        if float(getattr(field, "confidence", 0.0) or 0.0) < floor:
            return False
        # 来源相称这一维**只有一份实现**（`policies/collection.py::counts_as_got`）：
        # 权威字段（学信网核验 / 教务导入）由对话或行为推断写进来时不算拿到。
        # 不共用的后果真实出现过：采集清单说"还差专业"，这里却按"键在"放行，
        # 用户带着一条没核验的学籍离开①，之后再没有人回来要它。
        return counts_as_got(key, field, rules=rules)

    # "拿到了"的门槛比"覆盖"更低。来源相称只作用于**权威字段**，
    # 非权威字段（兴趣 / 目标方向这类本来就该从对话来的）口径完全不变。
    missing = tuple(key for key in key_fields if not got(key))
    coverage = 1.0 - len(missing) / len(key_fields)
    # 整体把握的计算不变：所有字段把握度的均值（含非关键字段）。
    confidences = [
        float(getattr(field, "confidence", 0.0) or 0.0) for field in by_key.values()
    ]
    overall = sum(confidences) / len(confidences) if confidences else 0.0
    ready = coverage >= coverage_threshold and overall >= overall_threshold
    return CollectionGate(ready=ready, coverage=coverage, overall=overall, missing=missing)


__all__ = ["CollectionGate", "evaluate_gate"]
