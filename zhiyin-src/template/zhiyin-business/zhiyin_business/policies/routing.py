"""意图识别与环节判定规则（轴 B）。

对应：识别用户意图 → 判定当前环节；判定不确定时必须回落到
澄清追问，不允许"猜一个环节硬跳"（产品硬约束）。

与 `ports/orchestrator.py` 的关系：Orchestrator 是**调用方**，本模块是
**规则本身**。Orchestrator 负责读黑板、调规则、落库、发事件；规则只回答
"这条消息属于哪个意图""该进哪个环节"。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType, StageDecision


class IntentPolicy(ABC):
    """把一条用户消息归类为意图。"""

    @abstractmethod
    async def classify(self, *, message: str, blackboard: BlackboardView) -> IntentType:
        """识别意图。规则优先 + 关键词/模型兜底；不确定时返回 FREE_CHAT。"""


class StagePolicy(ABC):
    """由意图与黑板状态判定目标环节。"""

    @abstractmethod
    async def decide(
        self,
        *,
        blackboard: BlackboardView,
        intent: IntentType,
        message: str,
    ) -> StageDecision:
        """判定环节。

        契约要求：
        - 判定不确定时置 `need_clarify=True` 并给出 `clarify_question`，
          由调用方渲染澄清追问，而不是推进环节；
        - `confidence` 必须如实反映把握程度，调用方按阈值决定是否追问。
        """
