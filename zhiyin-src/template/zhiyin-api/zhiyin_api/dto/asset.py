"""资产与导出 DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import AssetType, PlanRole


class AssetVersionView(BaseModel):
    """资产版本视图（R-API-005）。前端据此展示"v1→v2 的差异"。"""

    model_config = ConfigDict(extra="forbid")

    asset_type: AssetType
    asset_id: str
    version: int
    created_at: datetime
    depends_on_profile_keys: list[str] = Field(default_factory=list)
    diff_from_previous: Optional[str] = None


class ReportTocItemView(BaseModel):
    """报告目录项。`id` 与对应 `ReportSectionView.id` 相同，用于锚点跳转。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str


class ReportDimensionItemView(BaseModel):
    """15 维里的单维。**逐字段声明**而不是 `dict`：前端要按 `tag` 上色、
    按 `evidence` 做可溯源展示，字段名一旦漂移，界面会静默变成空白。"""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(description="维度序号 1-15")
    name: str = Field(description="维度名，如 兴趣倾向")
    tag: str = Field(description="维度标签：优势 / 短板 / 待验证")
    conclusion: str
    evidence: str = Field(description="证据引用，必须可溯源")


class ReportSectionView(BaseModel):
    """报告正文的一个分组（自我画像 / 职业环境 / 决策与风险）。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="锚点 id")
    title: str = Field(description="分组展示名")
    method: str = Field(default="", description="支撑该分组的方法论")
    items: list[ReportDimensionItemView] = Field(default_factory=list)


class ReportFullTextView(BaseModel):
    """完整报告页正文（只读资产视图，不承载实时对话）。

    形状的变迁：`toc` / `sections` 原来是 `list[dict[...]]`，属于"契约里有这个字段、
    但没人知道里面是什么"。代价在两处真实发生过：后端按 `anchor/group/group_method`
    写、前端按 `id/title/body` 读，两边都没错，只是从来没对上过 —— 而 `dict` 类型
    让这种错在编译期完全不可见。现在逐字段声明，前端类型由它生成。
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str
    version: int
    generated_at: datetime
    toc: list[ReportTocItemView] = Field(default_factory=list, description="左侧目录导航")
    sections: list[ReportSectionView] = Field(
        default_factory=list, description="按分组切开的 15 维正文"
    )
    verdict: dict[str, Any] = Field(
        default_factory=dict, description="综合结论 {title, summary}"
    )
    swot: dict[str, Any] = Field(default_factory=dict, description="SWOT 四象限")
    methodologies: list[str] = Field(
        default_factory=list, description="本次使用的理论模型名"
    )
    sources: list[str] = Field(default_factory=list, description="事实来源清单")


class PlanGapView(BaseModel):
    """方案内的一条差距：要求 − 现状 = 差距 + 补齐建议。"""

    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(description="这条方向要求什么")
    current_state: str = Field(default="", description="你现在在哪")
    suggestion: str = Field(default="", description="怎么补")


class DirectionPlanView(BaseModel):
    """一套方向方案（主攻 / 平行 / 保底）。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    role: PlanRole = Field(description="主攻 / 平行 / 保底")
    name: str
    target_desc: str = Field(default="", description="目标描述")
    match_score: float = Field(default=0.0, description="匹配度（解释性分值，非严谨算法）")
    gaps: list[PlanGapView] = Field(default_factory=list)
    fit_reason: str = Field(default="", description="契合依据")
    main_risk: str = Field(default="", description="主要风险")
    selected: bool = Field(default=False, description="是不是当前选中那一套")
    selected_at: Optional[datetime] = None
    revocable: bool = Field(default=True, description="恒为 True：选择随时可撤回")


class DirectionPlanListView(BaseModel):
    """三套方案 + "现在选的是哪一套"。

    `selected_id` 单独给一份，是因为前端要用它做高亮：只靠 plans[].selected 也能算，
    但"当前选择"在产品口径里是一个独立事实（可撤回、可对比），
    让它显式存在，界面上就不会出现"两套都亮着"这种状态。
    """

    model_config = ConfigDict(extra="forbid")

    plans: list[DirectionPlanView] = Field(default_factory=list)
    selected_id: Optional[str] = None
    match_score_method: str = Field(
        default="三叶草契合度 × 可达性",
        description="匹配度口径说明 —— 分值必须能解释，所以口径要对用户可见",
    )


class ActionTaskView(BaseModel):
    """行动任务：颗粒度是"今天/本周勾得掉"。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(description="勾选时回传的标识（阶段名:任务文本）")
    text: str
    phase: str = Field(default="", description="所属阶段名")
    due_date: Optional[datetime] = None
    done: bool = False
    done_at: Optional[datetime] = None


class ActionPhaseView(BaseModel):
    """行动阶段：一段时间的里程碑与它下面的任务。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    date_range: str = ""
    tag: str = ""
    tasks: list[ActionTaskView] = Field(default_factory=list)


class ActionPlanView(BaseModel):
    """行动计划正文（只读资产视图）。

    `has_plan=False` 是"还没有计划"（③ 还没走完），与"有计划但没有任务"是两件事 ——
    界面上必须是两句话，所以这里用 has_plan 显式区分，而不是让前端去猜空数组的含义。
    """

    model_config = ConfigDict(extra="forbid")

    has_plan: bool = False
    id: str = ""
    plan_id: Optional[str] = Field(default=None, description="关联的方向方案 id")
    phases: list[ActionPhaseView] = Field(default_factory=list)
    next_task: Optional[ActionTaskView] = Field(
        default=None, description="第一件还没勾掉的任务 —— 界面上的'现在这一件'"
    )
    reminders_synced: bool = Field(default=False, description="关键节点是否已写入日历")
    exported_at: Optional[datetime] = None


class ActionTaskDoneRequest(BaseModel):
    """勾掉 / 取消勾选一个行动任务。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    done: bool = True


class CalendarNodeView(BaseModel):
    """关键节点日历里的一条。

    规划师写入（④ 行动环节的 reminders）、教练读取、工作台展示 —— 三处看的是**同一份**。
    此前只有写没有读：库里躺着节点，界面上没有任何一处能看到它们。
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    title: str
    due_at: Optional[datetime] = None
    source: Literal["planner", "coach", "manual"] = Field(
        default="planner", description="谁写进来的：规划师 / 教练 / 用户自己"
    )
    related_task_text: str = Field(default="", description="这条节点对应哪件事")


class TrackEventView(BaseModel):
    """跟踪时间线里的一条：复盘环节的载体。

    类型只有五种（里程碑完成 / 提醒 / 警告 / 学期复盘 / 教练消息），
    由内核契约定死 —— 界面上不同基调的展示依赖它，不能是自由字符串。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal[
        "milestone_done", "reminder", "warning", "semester_review", "coach_message"
    ]
    title: str
    detail: str = ""
    occurred_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    related_task_id: Optional[str] = None
    related_stage: Optional[str] = None


class ExportRequest(BaseModel):
    """导出请求。"""

    model_config = ConfigDict(extra="forbid")

    asset_type: AssetType
    format: Literal["pdf", "docx"] = "pdf"


class ExportResultView(BaseModel):
    """导出结果。

    `message` 会原样显示在用户面前，所以它必须是一句用户能照做的话 ——
    默认值不再写"仅预留导出入口"这种只有我们知道什么意思的说法。
    """

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    message: str = "导出还在准备中：现在可以用「打印 / 存成 PDF」把这一版存下来。"
    object_key: Optional[str] = None
