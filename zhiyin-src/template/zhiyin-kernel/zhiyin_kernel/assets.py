"""资产与跟踪类契约。

对应 15 维报告 / 方向方案 / 行动计划 / 跟踪与成就。
字段结构以设计文档为准，第一期不追求索引与分区优化。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import PlanRole


class Verdict(BaseModel):
    """报告综合结论。"""

    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str


class Swot(BaseModel):
    """SWOT。每项不少于 2 条。"""

    model_config = ConfigDict(extra="forbid")

    strength: list[str] = Field(default_factory=list)
    weakness: list[str] = Field(default_factory=list)
    opportunity: list[str] = Field(default_factory=list)
    risk: list[str] = Field(default_factory=list)


class ReportDimensionItem(BaseModel):
    """15 维中的单维。"""

    model_config = ConfigDict(extra="forbid")

    index: int
    name: str
    tag: str = Field(description="维度标签，如优势/短板/待验证")
    conclusion: str
    evidence: str = Field(description="证据引用，必须可溯源")


class ReportDimensionGroup(BaseModel):
    """15 维分组：自我画像 6 / 职业环境 5 / 决策与风险 4。"""

    model_config = ConfigDict(extra="forbid")

    group: Literal["SELF-PORTRAIT", "JOB-MARKET", "DECISION-RISK"]
    group_method: str = Field(description="该分组支撑的方法论")
    items: list[ReportDimensionItem] = Field(default_factory=list)


class GapClaim(BaseModel):
    """差距认领记录。诊断 → 决策的衔接点。"""

    model_config = ConfigDict(extra="forbid")

    gap_id: str
    label: str = Field(
        default="",
        description="用户认领的是哪一条（他自己点的那句话），复盘与报告里要能读回来",
    )
    claimed_at: datetime


class Report(BaseModel):
    """15 维诊断报告。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    version: int
    generated_at: datetime
    verdict: Verdict
    swot: Swot
    dimensions: list[ReportDimensionGroup] = Field(default_factory=list)
    gap_claims: list[GapClaim] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list, description="事实来源，如学职平台/JD")
    methodologies: list[str] = Field(default_factory=list, description="本次使用的理论模型")


class PlanGap(BaseModel):
    """方案内的差距条目：要求 − 现状 = 差距 + 补齐建议。"""

    model_config = ConfigDict(extra="forbid")

    requirement: str
    current_state: str
    suggestion: str


class DirectionPlan(BaseModel):
    """方向方案。主攻/平行/保底三套，选择可撤回。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    report_id: Optional[str] = Field(default=None, description="关联的诊断报告 id")
    role: PlanRole
    name: str
    target_desc: str = Field(description="目标描述")
    match_score: float = Field(description="匹配度，解释性分值，非严谨算法")
    match_method: str = Field(
        default="",
        description="匹配度口径（同一批方案共用一句），如「三叶草契合度 × 可达性」",
    )
    gaps: list[PlanGap] = Field(default_factory=list)
    fit_reason: str = Field(description="契合依据")
    main_risk: str = Field(description="主要风险")
    selected: bool = False
    selected_at: Optional[datetime] = None
    revocable: bool = Field(default=True, description="可撤回，恒为 True")


class ActionTask(BaseModel):
    """行动任务。颗粒度要求"今天/本周勾得掉"。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        default="",
        description=(
            "任务标识。勾选 / 取消按它定位 —— 用任务文本当标识时，"
            "同一阶段里两条同名任务会互相顶掉。老数据没有这一列，"
            "仓储侧保留「阶段名:任务文本」作为回落口径。"
        ),
    )
    text: str
    due_date: Optional[datetime] = None
    done: bool = False
    done_at: Optional[datetime] = None


class ActionPhase(BaseModel):
    """行动阶段。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    date_range: str
    tag: str = Field(default="", description="阶段标签，如秋招投递/笔试冲刺")
    tasks: list[ActionTask] = Field(default_factory=list)


class ActionPlan(BaseModel):
    """行动计划。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    plan_id: Optional[str] = Field(default=None, description="关联的方向方案 id")
    phases: list[ActionPhase] = Field(default_factory=list)
    reminders_synced: bool = False
    exported_at: Optional[datetime] = None


class TrackEvent(BaseModel):
    """跟踪时间线事件。复盘产出的载体。

    **第一期不落表**：`FunctionService` 用进程内登记承载（P0 形态），
    所以数据库里没有对应的表。实现持久化时再建 —— 表跟着实现走，
    不走在实现前面（一张 0 行的表看起来像"这个能力已经有了"）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    type: Literal[
        "milestone_done", "reminder", "warning", "semester_review", "coach_message"
    ]
    title: str
    detail: str = ""
    occurred_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    related_task_id: Optional[str] = None
    related_stage: Optional[str] = None


class Achievement(BaseModel):
    """成就。只由行为日志驱动，防自嗨。

    **永远不落表**：成就是每次从行为日志**实时推导**出来的，不是一份独立记录。
    落一张成就表等于给它开了第二个事实来源，越往后越对不上
    （行为日志是只追加的，成就是推导结果）。

    注意这里**没有** `driven_by_behavior_log_only` 这类恒为真的标记字段：
    它自带默认值、又没有任何读取者，表达的是上面这段话已经说清的口径，
    只会让"成就模型有哪些字段"多一个假答案。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    badge_key: str
    unlocked: bool = False
    unlocked_at: Optional[datetime] = None


class CalendarNode(BaseModel):
    """关键节点日历条目。

    放在 contracts 而不是业务层：它是**跨层共用的数据形状**（规划师写入、
    教练读取、工作台展示）。若留在业务层，基础设施层就会反向引用业务模型，
    破坏单向依赖。

    **第一期不落表**：与跟踪时间线同样，现在由 `FunctionService` 的进程内登记
    承载；等真正要持久化时再建表，形状不变。
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    user_id: str = ""
    title: str
    due_at: Optional[datetime] = None
    source: Literal["planner", "coach", "manual"] = "planner"
    related_task_text: str = ""
