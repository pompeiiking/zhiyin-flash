"""黑板四件套契约。

黑板书 = 画像（活状态）+ 行为日志 + 会话记忆 + 资产版本影响面。
对应数据库表：profile_field / profile_gap / behavior_log / conversation_memory
/ asset_version / task_session。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import (
    AssetType,
    BehaviorEventType,
    LoopStage,
    PathFocus,
    ProfileSource,
    TaskStatus,
)


class ProfileField(BaseModel):
    """画像字段 · 活状态的最小单位。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="字段键，如 major / skills / interest（取数用，不直接展示）")
    label: str = Field(
        default="",
        description=(
            "这个字段用中文该怎么称呼（如「专业」「兴趣方向」）。"
            "字段键由模型自由生成（`interest_direction` 这种），"
            "界面拿不到中文名就只能把英文键摆给用户看 —— 名字必须跟着数据一起存"
        ),
    )
    value: Any = Field(description="字段值，结构由画像 schema 决定")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    source: ProfileSource = Field(description="来源")
    updated_at: datetime = Field(description="更新时间")
    evidence: list[str] = Field(default_factory=list, description="证据来源引用")


class ProfileGap(BaseModel):
    """画像缺口。用于采集追问与工作台展示。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="缺口字段键（取数用，不直接展示）")
    label: str = Field(default="", description="缺口的展示名（如「实习经历」）")
    reason: str = Field(description="为什么算缺口")
    suggested_next_action: str = Field(description="建议的下一步采集动作")


class Profile(BaseModel):
    """个人画像（活状态）。不因首次建档结束而冻结。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    version: int = Field(default=1, description="画像整体版本")
    updated_at: datetime
    fields: list[ProfileField] = Field(default_factory=list)
    gaps: list[ProfileGap] = Field(default_factory=list)


class BehaviorLog(BaseModel):
    """行为日志。北极星指标的唯一事实来源。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    event_type: BehaviorEventType
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    related_asset_ids: list[str] = Field(default_factory=list)


class UserNote(BaseModel):
    """用户自己写下的东西（自建待办 / 写下的目标）。

    为什么它得有自己的表，而不是塞进会话记忆
    ----------------------------------------
    会话记忆是按任务会话维护的摘要，`loop_stage` 还参与"现在走到哪一环节"的判断。
    把待办塞进去，等于给"当前阶段"注水——一个用户随手写的待办会把阶段算歪。

    它也不是行为日志：行为日志记的是"发生了什么"（点了、改了、完成了），
    这里记的是**用户的原话**。两者都能当信号读，但只有后者能被人引用：
    "因为你写了「想冲秋招」"里的那半句，必须是他自己写下过的字。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    kind: str = Field(default="todo", description="todo / goal：自建待办还是写下的目标")
    text: str = Field(description="用户的原话，采集策略直接从它里面读线索")
    done: bool = Field(default=False, description="只有待办有完成态；目标没有")
    created_at: datetime
    updated_at: datetime


class ConversationMemory(BaseModel):
    """会话记忆 · 按任务会话维护摘要，用于跨会话续接。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    task_id: Optional[str] = Field(default=None, description="为空表示无归属任务的自由会话")
    loop_stage: LoopStage
    lead_agent: str = Field(description="该会话当前主理智能体的 agent_id")
    summary: str = Field(default="", description="会话摘要")
    last_active_at: datetime


class ConversationTurn(BaseModel):
    """一轮对话的**原始记录**：用户说了什么、哪个主理答了什么。

    为什么与 `ConversationMemory` 分开：记忆是**累积摘要**（给模型续接用），
    它答不了两件事 ——

    · 会话列表点进去"这条会话发生过什么"（要逐轮原文，不是一段摘要）；
    · 复盘与审计"他当时是怎么说的"（摘要里那句已经是模型改写过的）。

    此前用户自己说的话**一个字都没落库**：库里只有模型的原始输出与一段摘要。
    所以会话列表能列、点进去却是空的 —— 那不是界面没做，是数据没存。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    task_id: Optional[str] = Field(default=None, description="为空表示无归属任务的自由会话")
    role: Literal["user", "agent"] = Field(description="谁说的")
    text: str
    loop_stage: LoopStage
    agent_id: str = Field(default="", description="role=agent 时是哪位主理")
    created_at: datetime


class AssetVersion(BaseModel):
    """资产版本与影响面。

    depends_on_profile_keys 是影响面传播的唯一依据：
    画像字段更新后，只重算命中的资产，版本 +1。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    asset_type: AssetType
    version: int = Field(description="从 1 开始递增")
    created_at: datetime
    depends_on_profile_keys: list[str] = Field(default_factory=list)
    diff_from_previous: Optional[str] = Field(
        default=None, description="v(n-1) → v(n) 的差异说明，首版为空"
    )


class TaskSession(BaseModel):
    """任务会话。可拆可续的载体：记录当前环节，而非"报告是否生成"。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    task_code: str = Field(description="首页任务入口 code，如 confused / verify_direction")
    task_name: str = Field(description="用户可见的任务名")
    loop_stage: LoopStage
    lead_agent: str
    path_focus: Optional[PathFocus] = Field(
        default=None,
        description="路径焦点（就业 / 考研 / 留学）。轴 A 单轨，混合路径时由会话携带",
    )
    status: TaskStatus = TaskStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
