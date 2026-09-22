"""交接规则与"换主理必须显式告知"。

三条产品硬约束之一：**换主理必须显式告知**。告知不是渲染层的事，而是规则层
的判定结果——`HandoffDecision.disclosure` 为空即视为违规，前端 `DisclosureRow`
据此渲染。这条链路过去因为没有规则归属而无法回归测试。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import HandoffDecision
from zhiyin_kernel.enums import LoopStage


class HandoffPolicy(ABC):
    """交接判定规则。"""

    @abstractmethod
    def decide(
        self,
        *,
        blackboard: BlackboardView,
        from_stage: LoopStage,
        from_agent: str,
        to_stage: LoopStage,
        to_agent: str,
        reason: str,
    ) -> HandoffDecision:
        """产出交接决策（含显式告知文案的构造依据）。"""

    @abstractmethod
    def disclosure_required(
        self,
        *,
        from_stage: LoopStage | None,
        from_agent: str | None,
        to_agent: str,
        conclusion_changed: bool = False,
        theory_changed: bool = False,
    ) -> bool:
        """是否需要显式告知。

        产品口径：换主理、换理论、结论变化三种情况都必须告知。本方法把
        "什么时候算变化"收敛到一处，避免每个调用方各判一次。
        """
