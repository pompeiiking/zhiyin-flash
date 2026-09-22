"""核心对话页 DTO（三栏框架）。

- 左栏：会话管理（TaskSessionView / SessionListView）
- 中栏：对话 + 行为引导（ConversationMessageView / ConversationTurnView）
- 右栏：微循环管线卡三态（PipelineCardView）

长内容不进对话流：对话消息只说最短结论，全文走右栏卡与工作台资产。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_api.dto.asset import AssetVersionView
from zhiyin_api.dto.common import (
    AgentBadgeView,
    BehaviorGuideView,
    DisclosureView,
    TheoryRefView,
)
from zhiyin_kernel.enums import LoopStage, TaskStatus


class TaskEnterRequest(BaseModel):
    """进入任务。task_code 取自 bootstrap 的任务入口。"""

    model_config = ConfigDict(extra="forbid")

    task_code: str


class MessageRequest(BaseModel):
    """一轮用户输入。支持会话续接（R-API-003）。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    message: str
    client_msg_id: Optional[str] = Field(default=None, description="前端幂等键")


class ChartPointView(BaseModel):
    """图上的一个点。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    value: float


class ChartView(BaseModel):
    """主理在对话里给的那张图。

    值来自服务端**实测数据**（画像各维把握、方案匹配度…），不是模型写的数字 ——
    图上的每个点都能追回它来自哪条记录。
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["bars"] = "bars"
    title: str = ""
    unit: str = ""
    points: list[ChartPointView] = Field(default_factory=list)


class IntelRefView(BaseModel):
    """对话里引用的一条外部情报（可点回原页面）。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = ""
    kind_label: str = ""
    source_name: str = ""
    source_url: str = ""


class ConversationMessageView(BaseModel):
    """对话气泡。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["agent", "user", "system"]
    text: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    theory_refs: list[TheoryRefView] = Field(
        default_factory=list, description="可点开的理论标签"
    )
    chart: Optional[ChartView] = Field(
        default=None, description="这一轮顺手给的图；没有就是 null"
    )
    intel_refs: list[IntelRefView] = Field(
        default_factory=list, description="这一轮用到的外部情报来源，可点回原页面"
    )
    created_at: Optional[datetime] = None


class PipelineCardView(BaseModel):
    """右栏管线卡（①-⑤ 每环节一卡）。

    三态：当前产出 / 可展开理论模型 / 可展开评价状态。
    """

    model_config = ConfigDict(extra="forbid")

    stage: LoopStage
    title: str
    active: bool = Field(default=False, description="是否为当前环节，前端高亮")
    status: Literal["empty", "in_progress", "done"] = "empty"
    current_output: Optional[dict[str, Any]] = Field(
        default=None, description="态①：当前产出摘要"
    )
    theory_models: list[TheoryRefView] = Field(
        default_factory=list, description="态②：可展开的理论模型"
    )
    evaluation: Optional[dict[str, Any]] = Field(
        default=None, description="态③：可展开的评价状态"
    )


class ConversationTurnView(BaseModel):
    """一轮回复的完整视图。

    对应编排调用链的返回：最短结论 + 显式告知 + 行为引导 + 管线卡。
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    stage: LoopStage
    badge: AgentBadgeView = Field(description="顶栏主理徽章：谁在帮我 + 依据哪些理论")
    messages: list[ConversationMessageView] = Field(default_factory=list)
    disclosure: Optional[DisclosureView] = Field(
        default=None, description="换主理/换理论/结论变化的显式告知行"
    )
    guide: BehaviorGuideView = Field(
        description="行为引导：question/options/task/reminder 四选一"
    )
    pipeline_cards: list[PipelineCardView] = Field(default_factory=list)
    changed_assets: list[AssetVersionView] = Field(
        default_factory=list, description="本轮变化的资产版本，用于工作台刷新"
    )


class TaskSessionView(BaseModel):
    """左栏会话项。按"任务/环节"命名，不按 agent 名排布。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_name: str
    stage: LoopStage
    stage_label: str = Field(description="环节中文名，用于左栏命名")
    lead_agent_name: str = ""
    status: TaskStatus = TaskStatus.ACTIVE
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="闭环进度")
    last_active_at: Optional[datetime] = None


class SessionListView(BaseModel):
    """左栏会话列表。"""

    model_config = ConfigDict(extra="forbid")

    sessions: list[TaskSessionView] = Field(default_factory=list)
    current_task_id: Optional[str] = None
