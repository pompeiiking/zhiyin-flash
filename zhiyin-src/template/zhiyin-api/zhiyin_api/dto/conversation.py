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
    """一轮用户输入。支持会话续接（R-API-003）。

    `option_id` / `option_value` 是"这一轮点的是哪个选项"。

    为什么不能只发选项的**显示文字**：界面上那几个按钮是后端上一轮给的
    `guide.options`，它们有稳定的身份（`option_id`）与机器可读的取值（`value`）。
    只把 label 当一句话发回来，这一轮就退化成了自由文本 ——
    编排放器分不清"用户明确选了「我现在还在念书」"和"用户随口说了这几个字"，
    于是可能把同一个问题再问一遍。用户看到的是：点了选项，问题原样又回来了。
    这两个字段都是可选的：手打的那一轮本来就只有一个 message。
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    message: str
    client_msg_id: Optional[str] = Field(default=None, description="前端幂等键")
    option_id: Optional[str] = Field(
        default=None, description="这一轮点了哪个选项（guide.options[].option_id）"
    )
    option_value: Any = Field(
        default=None,
        description="该选项的机器可读取值（guide.options[].value）；没有就是 None",
    )
    material_ids: list[str] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "这一轮一起交上去的材料（`POST /app/conversation/material` 的返回 id）。"
            "材料正文不进 `message`：它只在服务端拼进这一轮的模型输入 —— "
            "把一份简历几百段塞进对话气泡，用户要读的是主理的回话，不是自己交的原文"
        ),
    )


class ConversationMaterialView(BaseModel):
    """一次材料上收的回执（文件传上来的结果）。

    **不含正文**：正文回给前端就等于把文件又摊在对话框里了。
    前端拿到的是"它是什么"（名字 / 原始大小 / 读到多少字），够它画一枚材料卡。
    """

    model_config = ConfigDict(extra="forbid")

    material_id: str
    name: str = ""
    size: int = Field(default=0, description="原文件字节数")
    chars: int = Field(default=0, description="读出来的正文字数")


class IntelRefView(BaseModel):
    """对话里引用的一条外部情报（可点回原页面）。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = ""
    kind_label: str = ""
    source_name: str = ""
    source_url: str = ""


class RenderableView(BaseModel):
    """对话里的一块**可视件**：图 / 时间线 / 对比矩阵……

    前端按 `kind` 选组件画（缺组件时应当如实跳过，不要把 payload 直接摊给用户）。
    服务端只放**注册过并通过校验**的类型（注册表在
    `zhiyin_business/policies/renderers.py`）：`kind` 没注册过、`payload` 形状不对，
    在编排器那边就已经丢掉了，不会走到这里。
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    title: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[IntelRefView] = Field(
        default_factory=list, description="这一件用到的外部来源，可点回原页面"
    )


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
    renderables: list[RenderableView] = Field(
        default_factory=list,
        description=(
            "这一轮要摆给用户看的可视件：主理自己调工具产出的，"
            "或这一环节默认补的那张。前端按 kind 选组件渲染，数值由服务端填"
        ),
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
