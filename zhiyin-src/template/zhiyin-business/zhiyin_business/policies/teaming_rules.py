"""动态组队默认实现：主理从任务入口动态读取。"""

from __future__ import annotations

from zhiyin_business.policies.teaming import LeadPolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType, LeadDecision
from zhiyin_business.ports.registry import RegistryService
from zhiyin_kernel.enums import AxisAStage, LoopStage
from zhiyin_kernel.errors import ResourceNotFound


class RegistryLeadPolicy(LeadPolicy):
    """按目标环节从任务入口解析主理。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, registry: RegistryService) -> None:
        self._registry = registry

    async def select(
        self,
        *,
        blackboard: BlackboardView,
        axis_a: AxisAStage,
        stage: LoopStage,
        intent: IntentType,
    ) -> LeadDecision:
        for entry in await self._registry.list_task_entries():
            if entry.target_stage == stage and entry.lead_agent:
                return LeadDecision(
                    lead_agent=entry.lead_agent,
                    assistant_agents=[],
                    info_scout_required=stage in {LoopStage.DIAGNOSE, LoopStage.ACT},
                    reason=f"当前处于{entry.label}，由该任务入口的默认主理接手",
                )
        raise ResourceNotFound(f"没有为环节 {stage.value} 配置任务入口主理")


__all__ = ["RegistryLeadPolicy"]
