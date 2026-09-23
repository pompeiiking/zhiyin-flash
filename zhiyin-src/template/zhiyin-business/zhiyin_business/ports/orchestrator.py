"""编排器（轴 C）契约。

职责：
1. 识别用户意图 → 判定当前环节（轴 B）；
2. 按（轴 A 阶段 × 轴 B 环节 × 意图）选择主理（及协理 / 信息侦查员）；
3. 定义跨智能体交接；
4. 维护黑板一致性（委托给黑板服务的事件订阅）；
5. 调度主动事件；
6. 生成"显式告知"文案。

实现要求见 R-BIZ-001 ~ R-BIZ-005。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.blackboard import AssetVersion, TaskSession
from zhiyin_kernel.enums import AxisAStage, LoopStage
from zhiyin_business.contracts.common import (
    AgentBadge,
    BehaviorGuide,
    ConversationMessage,
    Disclosure,
)
from zhiyin_business.ports.blackboard import BlackboardView


class IntentType(str, Enum):
    """用户意图分类。

    对应首页任务入口与兜底"直接开聊"。
    """

    CONFUSED = "confused"                  # 还不太清楚自己适合什么
    VERIFY_DIRECTION = "verify_direction"  # 想验证某方向行不行
    UNDECIDED = "undecided"                # 几个方向拿不准
    HOW_TO_ACT = "how_to_act"              # 定了方向不知道怎么动
    STUCK = "stuck"                        # 执行卡住了 / 没进展
    REVIEW_DUE = "review_due"              # 好久没管了 / 该复盘了
    FREE_CHAT = "free_chat"                # 直接开聊，需意图识别


class StageDecision(BaseModel):
    """环节判定结果。判定不确定时必须用澄清追问，不硬跳。"""

    model_config = ConfigDict(extra="forbid")

    stage: Optional[LoopStage] = Field(default=None, description="判定出的环节")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Literal["intent", "progress", "fallback", "clarify", ""] = Field(
        default="",
        description=(
            "这个结论是怎么来的：`intent`=用户这句话明确命中了意图映射（他说的算）；"
            "`progress`=按资产与行为推出的下一步；`fallback`=都没命中，留在当前环节；"
            "`clarify`=连环节都没有，先澄清。"
            "**调用方要能区分这三种**：例如采集门槛只该顶掉后两种 —— "
            "用户主动说「我迷茫、想重新过一遍自己」时把他顶去诊断，等于不听他说话。"
        ),
    )
    need_clarify: bool = Field(default=False, description="是否回落到澄清追问")
    clarify_question: Optional[str] = None


class LeadDecision(BaseModel):
    """主理选择结果。"""

    model_config = ConfigDict(extra="forbid")

    lead_agent: str = Field(description="主理智能体 agent_id")
    assistant_agents: list[str] = Field(default_factory=list, description="协理")
    info_scout_required: bool = Field(
        default=False, description="是否需要信息侦查员供外部事实"
    )
    reason: str = Field(default="", description="选择依据，用于显式告知")


class HandoffDecision(BaseModel):
    """交接结果。换主理必须显式告知。"""

    model_config = ConfigDict(extra="forbid")

    from_stage: Optional[LoopStage] = None
    to_stage: LoopStage
    from_agent: Optional[str] = None
    to_agent: str
    reason: str = ""
    disclosure: Optional[Disclosure] = None


class TurnRequest(BaseModel):
    """一次用户回合的输入。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    task_id: str
    message: str
    client_msg_id: Optional[str] = None
    option_id: Optional[str] = Field(
        default=None, description="这一轮点的是哪个选项（上一轮 guide.options 的 id）"
    )
    option_value: Any = Field(
        default=None, description="该选项的机器可读取值；手打的一轮为 None"
    )
    attachment_name: str = Field(
        default="",
        description="这一轮带上来的材料名（只用于给模型交代这段正文是哪来的）",
    )
    attachment_text: str = Field(
        default="",
        description=(
            "材料的正文。**只进模型输入**：`message` 才是落库与显示的那一句 —— "
            "把一份简历几百段塞进对话流，用户要读的是主理的回话，不是自己刚交的东西"
        ),
    )


class TurnResult(BaseModel):
    """一次用户回合的输出。

    严格对应"单轮回复骨架"：
    读黑板 → 环节判定 → 选主理 → 理论链产出 → 行为引导收尾。
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    session: TaskSession
    stage: LoopStage
    badge: AgentBadge = Field(description="现在是谁在帮我、依据什么")
    messages: list[ConversationMessage] = Field(
        default_factory=list, description="本轮回复消息，只含最短结论"
    )
    disclosure: Optional[Disclosure] = Field(
        default=None, description="换主理 / 换理论 / 结论变化时的显式告知"
    )
    guide: BehaviorGuide = Field(description="行为引导收尾，必须四选一")
    asset_versions: list[AssetVersion] = Field(
        default_factory=list, description="本轮产生或变化的资产版本"
    )


class Orchestrator(ABC):
    """编排器 Port。"""

    @abstractmethod
    async def read_blackboard(self, user_id: str, task_id: str) -> BlackboardView:
        """读取黑板快照。所有环节进入前都必须先读黑板。"""

    @abstractmethod
    async def detect_intent(self, user_id: str, message: str) -> IntentType:
        """识别用户意图。规则优先 + 关键词/LLM 兜底。"""

    @abstractmethod
    async def detect_stage(
        self, user_id: str, task_id: str, intent: IntentType
    ) -> StageDecision:
        """判定目标环节（轴 B）。"""

    @abstractmethod
    async def infer_axis_a(self, user_id: str, task_id: str) -> AxisAStage:
        """推断轴 A 阶段。

        口径：五段全量，
        "规则优先 + LLM 兜底"。规则写在 `policies/`，本方法只负责调规则、
        必要时走模型兜底；**前台不让用户自选阶段**。
        """

    @abstractmethod
    async def select_lead(
        self,
        user_id: str,
        task_id: str,
        axis_a: AxisAStage,
        stage: LoopStage,
        intent: IntentType,
    ) -> LeadDecision:
        """选择主理 / 协理 / 信息侦查员（轴 A × 轴 B × 意图）。"""

    @abstractmethod
    async def handoff(
        self, user_id: str, task_id: str, to_stage: LoopStage, reason: str
    ) -> HandoffDecision:
        """执行交接并生成显式告知。"""

    @abstractmethod
    async def enter_task(self, user_id: str, task_code: str) -> TaskSession:
        """从首页任务入口进入任务：判环节 → 选主理 → 建会话或续接。

        同一任务已有进行中的会话时返回既有会话（续接），否则新建。
        任务名 / 目标环节 / 默认主理取动态资源 task_entries；
        目标环节为空的入口（直接开聊）回落 ① 采集 + 建档分析师。
        """

    @abstractmethod
    async def handle_message(self, request: TurnRequest) -> TurnResult:
        """处理一次用户输入，跑完"单轮回复骨架"。"""
