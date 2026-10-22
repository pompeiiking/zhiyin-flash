"""黑板四件套契约。

黑板书 = 画像（活状态）+ 行为日志 + 会话记忆 + 资产版本影响面。
对应数据库表：profile_field / profile_gap / behavior_log / conversation_memory
/ asset_version / task_session。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from zhiyin_kernel.evidence_assessment import EvidenceAssessment

from zhiyin_kernel.enums import (
    AssetType,
    BehaviorEventType,
    LoopStage,
    PathFocus,
    ProfileClueStatus,
    ProfileEntryStatus,
    ProfileEntryType,
    ProfileSource,
    ProfileVerification,
    TaskStatus,
)


class ProfileField(BaseModel):
    """画像里的一条记录（活状态的最小单位）。

    记录结构见《个人画像设计-2026-10-20》第 4 节：一条记录除了「键值」，
    还要能回答六件事 —— 它属于哪一类内容、内容结构是什么、原话/资料在哪、
    来源方式与核实状态分别是什么、何时知道/何时发生/何时仍适用、以及它现在是
    有效、被更正、存在冲突还是已撤回。

    兼容阶段保留 `confidence`：它不再充当真实性、熟练度或写权限的共同开关，
    也不直接展示成百分比。新字段全部有默认值，老数据读出来仍是合法记录
    （缺类别时由受控词表按键推导，缺核实状态时由来源推导）。
    """

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
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1（兼容字段，不再直接展示）")
    source: ProfileSource = Field(description="来源：这条信息从哪儿来")
    updated_at: datetime = Field(description="更新时间（何时知道这条记录）")
    evidence: list[str] = Field(default_factory=list, description="证据来源引用（原话/资料片段）")
    #: 内容类别：由受控词表按字段键推导，服务端写入时固化。
    entry_type: Optional[ProfileEntryType] = Field(
        default=None, description="内容类别（学习背景/兴趣/经历/能力/职业关注/价值取向/现实条件/补充信息）"
    )
    #: 类别专属的结构化值：兴趣的正负与情境、职业关注的关注状态、能力的证据类型等。
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="类型专属的结构化属性（受控键；不是任意模型输出）"
    )
    #: 核实状态：与来源分开表达，不用一个分数混合。
    verification: Optional[ProfileVerification] = Field(
        default=None, description="核实状态（自述/本人确认/资料记录/核验/待核实）"
    )
    status: ProfileEntryStatus = Field(
        default=ProfileEntryStatus.ACTIVE, description="当前状态：有效/已更正/冲突/过期/撤回"
    )
    #: 原话或资料来源引用：指向实际会话、材料片段或导入记录。
    origin_ref: str = Field(default="", description="原话或资料来源引用（不编造引用）")
    #: 三个时间分开：何时知道（updated_at）、何时发生（event_at）、何时仍适用（valid_from/valid_to）。
    valid_from: Optional[datetime] = Field(default=None, description="有效范围起点；未知不补成当前时间")
    valid_to: Optional[datetime] = Field(default=None, description="有效范围终点")
    event_at: Optional[datetime] = Field(default=None, description="事情发生的时间（不是记录时间）")
    #: 同一条记录的版本：并发更新与「我看到的是哪一版」的依据。
    entry_version: int = Field(default=1, ge=1, description="条目版本，从 1 开始")
    superseded_by: str = Field(default="", description="被哪条记录替代（修订关系）")
    evidence_assessment: EvidenceAssessment | None = None


class ProfileFieldRevision(BaseModel):
    """画像记录的历史版本 / 冲突提案（设计第 4、7 节）。

    当前值仍由 `biz_profile_field` 一行一键承载（旧 API 的兼容投影）；
    本模型只追加不改写：
      · 每次值被替代时，旧值进历史（status=superseded）；
      · 自动记忆遇到与当前值不一致的新说法时，不覆盖当前值，而是追加一条
        status=conflict 的提案，等待用户裁定（设计第 7 节“并存标记”）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="版本标识（服务端生成）")
    user_id: str = Field(description="归属账号")
    key: str = Field(description="字段键")
    label: str = Field(default="")
    value: Any = Field(description="这一版的值")
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: ProfileSource = Field(description="这一版从哪儿来")
    verification: Optional[ProfileVerification] = None
    status: ProfileEntryStatus = Field(
        default=ProfileEntryStatus.ACTIVE,
        description="这一版在历史里的状态：superseded / conflict / withdrawn 等",
    )
    evidence: list[str] = Field(default_factory=list)
    origin_ref: str = Field(default="")
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    event_at: Optional[datetime] = None
    entry_version: int = Field(default=1, ge=1, description="对应的条目版本")
    created_at: datetime = Field(description="这一版产生的时刻")
    replaced_at: Optional[datetime] = Field(default=None, description="被替代/裁定的时刻")
    change_reason: str = Field(default="", description="为什么产生这一版：给用户看的一句话")


class ProfileGap(BaseModel):
    """画像缺口。用于采集追问与工作台展示。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="缺口字段键（取数用，不直接展示）")
    label: str = Field(default="", description="缺口的展示名（如「实习经历」）")
    reason: str = Field(description="为什么算缺口")
    suggested_next_action: str = Field(description="建议的下一步采集动作")


class ProfileClue(BaseModel):
    """一条待验证线索（《个人画像设计-2026-10-20》第 3.2、7 节）。

    它**不是**画像事实：AI 对信息的有限理解单独保存，必须关联依据、标明适用范围。
    例如「喜欢弄清 bug 的原因」是兴趣体验，「可能关注机制与原因」是待验证线索，
    「适合算法工程师」则不能由此成立 —— 后者不是线索，是无依据的结论。

    为什么要有 `field_keys`：依据被更正、撤回或删除后，相关线索要能失效或等待
    重新分析。服务端按「这次改到的字段键 ∩ 线索声明的依据字段」判定，而不是靠
    重新读一遍对话去猜。

    `evidence` 与 `origin_ref` 分工同 `ProfileField`：evidence 是可回看的依据列表，
    这里不再额外存一份原话正文（原话在会话轮次里）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="线索标识（服务端生成）")
    user_id: str = Field(description="归属账号：线索也不跨账号可见")
    session_id: str = Field(default="", description="产生这条线索的会话（同一会话整体替换）")
    text: str = Field(description="线索正文：一句「可能……」的有限理解，不是结论")
    evidence: list[str] = Field(default_factory=list, description="依据引用（原话/资料片段）")
    field_keys: list[str] = Field(
        default_factory=list, description="这条理解依据哪些画像字段；这些字段变更时线索失效"
    )
    source: ProfileSource = Field(default=ProfileSource.ASSESSMENT, description="线索从哪儿来")
    status: ProfileClueStatus = Field(
        default=ProfileClueStatus.PROPOSED, description="待验证/已失效/已确认"
    )
    invalidated_reason: str = Field(default="", description="为什么失效：给用户看的一句话")
    created_at: datetime = Field(description="产生时间")
    updated_at: datetime = Field(description="最后变更时间")


class Profile(BaseModel):
    """个人画像（活状态）。不因首次建档结束而冻结。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    version: int = Field(default=1, description="画像整体版本")
    updated_at: datetime
    fields: list[ProfileField] = Field(default_factory=list)
    gaps: list[ProfileGap] = Field(default_factory=list)
    #: 待验证线索：与 fields 分开展示，界面要能说清「这是系统的理解，不是事实」。
    clues: list[ProfileClue] = Field(default_factory=list)
    #: 冲突提案：与当前值并存，等待用户裁定；不参与用途读取。
    conflicts: list[ProfileFieldRevision] = Field(default_factory=list)


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
    role: Literal["user", "agent", "system"] = Field(description="谁说的")
    text: str
    loop_stage: LoopStage
    renderables: list[dict[str, Any]] = Field(default_factory=list, description="服务端校验后的可视件快照")
    metadata: dict[str, Any] = Field(default_factory=dict, description="请求摘要、完整回包与提议身份；不直接作为模型事实")
    agent_id: str = Field(default="", description="role=agent 时是哪位主理")
    client_msg_id: str = Field(
        default="",
        description="前端给的幂等键。重发同一条消息时据此认出「这条已经答过了」，不再走一遍模型",
    )
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
    needs_recompute: bool = Field(
        default=False,
        description=(
            "画像变了、这一版还没跟着重算。**只标记，不升版** —— "
            "升版意味着「内容真的重算过」，而校验过的新正文是在下一次进入该环节时才产出的"
        ),
    )
    recompute_reason: str = Field(
        default="",
        description="为什么要重算：给用户看的一句话，说明是哪次画像更新让这一版过期了",
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
