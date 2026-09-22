"""交接与显式告知默认实现。"""

from __future__ import annotations

from zhiyin_business.contracts.common import Disclosure
from zhiyin_business.policies.handoff import HandoffPolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import HandoffDecision
from zhiyin_kernel.enums import LoopStage


class DisclosureHandoffPolicy(HandoffPolicy):
    """任何环节或主理变化都产出显式告知。"""

    IMPLEMENTATION_STATUS = "wired"

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
        changed = from_stage != to_stage or from_agent != to_agent
        disclosure = None
        if changed:
            disclosure = Disclosure(
                kind="lead_change" if from_agent != to_agent else "theory_change",
                text=reason or f"服务重点从 {from_stage.value} 转到 {to_stage.value}",
                from_agent=from_agent,
                to_agent=to_agent,
            )
        return HandoffDecision(
            from_stage=from_stage,
            to_stage=to_stage,
            from_agent=from_agent,
            to_agent=to_agent,
            reason=reason,
            disclosure=disclosure,
        )

    def disclosure_required(
        self,
        *,
        from_stage: LoopStage | None,
        from_agent: str | None,
        to_agent: str,
        conclusion_changed: bool = False,
        theory_changed: bool = False,
    ) -> bool:
        return (
            conclusion_changed
            or theory_changed
            or from_agent != to_agent
            or from_stage is None
        )


__all__ = ["DisclosureHandoffPolicy"]
