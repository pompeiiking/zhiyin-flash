"""动态组队规则：选主理 / 协理 / 信息侦查员（轴 A × 轴 B × 意图）。

产品主线要求"现在是谁在帮我、依据什么"必须能回答，
因此规则产出的 `LeadDecision.reason` 会被直接用于界面上的显式告知。

轴 A 口径已定稿：
五段全量、规则优先 + LLM 兜底、单轨 + 会话路径焦点。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType, LeadDecision
from zhiyin_kernel.enums import AxisAStage, LoopStage


class LeadPolicy(ABC):
    """主理选择规则。"""

    @abstractmethod
    async def select(
        self,
        *,
        blackboard: BlackboardView,
        axis_a: AxisAStage,
        stage: LoopStage,
        intent: IntentType,
    ) -> LeadDecision:
        """选择主理（及协理 / 信息侦查员）。

        约束：
        - 主理必须来自 `AgentRegistry`（动态资源），不得在代码里写死 agent_id；
        - 同一环节不同轴 A 阶段可以选不同主理，这是"同一环节不同服务深度"的落点；
        - `reason` 是给用户看的依据，不是内部日志。
        """
