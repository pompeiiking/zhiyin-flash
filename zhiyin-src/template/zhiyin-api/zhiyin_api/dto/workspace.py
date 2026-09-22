"""智能工作台 DTO（按 ①-⑤ 分层聚合）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_api.dto.common import TheoryRefView
from zhiyin_kernel.enums import LoopStage, ProfileSource


class ProfileFieldView(BaseModel):
    """画像里的一条字段（活状态的最小单位）。

    此前这里是 `dict[str, Any]`：契约只说"有 fields"，不说每条里有什么。
    前端要按 `confidence` 画把握度、按 `evidence` 做可溯源展示、按 `source`
    说明这条从哪来 —— 全是猜的字段名。现在逐字段声明。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="字段键，如 major / skills / interest（取数用，不直接展示）")
    label: str = Field(
        default="",
        description="字段的展示名（来自动态资源）；为空表示这份配置里没有它，界面回落到 key",
    )
    value: Any = Field(default=None, description="字段值，结构由画像 schema 决定")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: ProfileSource
    updated_at: datetime
    evidence: list[str] = Field(default_factory=list, description="证据来源引用")


class ProfileGapView(BaseModel):
    """画像缺口：还缺哪条、为什么算缺、建议怎么补。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="缺口字段键（取数用，不直接展示）")
    label: str = Field(
        default="",
        description=(
            "缺口的展示名（来自动态资源）；为空表示这份配置里没有它，界面回落到 key"
        ),
    )
    reason: str = Field(description="为什么算缺口")
    suggested_next_action: str = Field(default="", description="建议的下一步采集动作")


class ProfilePanelView(BaseModel):
    """① 画像状态：字段覆盖度 / 置信度 / 缺口 / 更新时间。"""

    model_config = ConfigDict(extra="forbid")

    coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="字段覆盖度")
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fields: list[ProfileFieldView] = Field(default_factory=list)
    gaps: list[ProfileGapView] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class StagePanelView(BaseModel):
    """②-⑤ 的节点卡。三态：当前评价 / 理论模型 / 历史 diff。"""

    model_config = ConfigDict(extra="forbid")

    stage: LoopStage
    title: str
    evaluation: str = ""
    theory_models: list[TheoryRefView] = Field(
        default_factory=list, description="该环节用到的理论模型（可点开看正文）"
    )
    version: Optional[int] = None
    diff: Optional[str] = Field(default=None, description="差异说明，如「因更新了 X，v1→v2 的变化」")
    updated_at: Optional[datetime] = None


class DependencyEdgeView(BaseModel):
    """依赖可视化（简版）。"""

    model_config = ConfigDict(extra="forbid")

    from_asset: str
    to_asset: str
    via_profile_keys: list[str] = Field(default_factory=list)


class CollectionItemView(BaseModel):
    """采集清单里的一条。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    source: str = Field(description="chsi / conversation / academic")
    why: str = Field(description="这条数据挡着哪一步判断 —— 给用户看的理由")
    got: bool = False
    available: bool = Field(default=True, description="这个源头现在能不能用")


class CollectionPanelView(BaseModel):
    """动态采集策略：还缺什么、去哪儿取、为什么是它。

    它不是"还差几条"的计数器，是**下一步该做什么**的判据：
    界面按 `by_source` 分组说"从哪取"，按 `items` 的顺序说"先取哪一条"。
    """

    model_config = ConfigDict(extra="forbid")

    missing: int = Field(default=0, description="还差几条")
    by_source: dict[str, int] = Field(default_factory=dict, description="每个源还差几条")
    blocked: list[str] = Field(default_factory=list, description="有缺口、但没有源头")
    next_source: Optional[str] = Field(default=None, description="下一步最该走的源头")
    items: list[CollectionItemView] = Field(default_factory=list)


class AcademicCourseView(BaseModel):
    """课表里的一门课（教务系统取回来的原样，不改口径）。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    teacher: str = ""
    weekday: int = Field(default=0, description="1=周一 … 7=周日；0 表示没解析出")
    start_period: int = 0
    end_period: int = 0
    weeks: str = ""
    place: str = ""
    credit: str = ""
    category: str = ""


class AcademicGradeView(BaseModel):
    """成绩单里的一条。等级制就照原样记，不换算。"""

    model_config = ConfigDict(extra="forbid")

    term: str = ""
    name: str
    credit: str = ""
    score: str = ""
    point: str = ""
    category: str = ""
    kind: str = ""


class AcademicPanelView(BaseModel):
    """学生自己导入的课表与成绩单。

    它不是一个数组而是一份**快照**：学校、学期、取数时刻，加上课与成绩。
    为什么要把"什么时候取的"一起给前端：课表会变（退课、调课、补考），
    界面必须能说出这份数据是哪一天的，否则用户没法判断它还算不算数。
    """

    model_config = ConfigDict(extra="forbid")

    school: str = ""
    source: str = Field(default="", description="按哪种版式读出来的：qz / zf / table / json")
    term: str = ""
    imported_at: str = ""
    note: str = Field(default="", description="导入时发现、但不足以拒绝的情况")
    courses: list[AcademicCourseView] = Field(default_factory=list)
    grades: list[AcademicGradeView] = Field(default_factory=list)


class AcademicImportRequest(BaseModel):
    """一次导入：贴进来的原文（课表、成绩单可各自为空）。

    长度上限不是"防用户"，是**防一次误操作把服务打满**：教务系统整页复制很容易
    带上几千行样式表，解析器是纯文本处理，几百 KB 的无意义输入会白烧 CPU。
    这里给一个宽到不会挡住真实用量的界（200 KB 量级），超了就让用户删掉无关部分 ——
    比默默接收再跑一遍解析更诚实。
    """

    model_config = ConfigDict(extra="forbid")

    courses: str = Field(
        default="",
        max_length=200_000,
        description="课表原文：页面整页复制 / 表格 / JSON",
    )
    grades: str = Field(default="", max_length=200_000, description="成绩单原文")
    school: str = Field(default="", max_length=120, description="学校名（可留空）")
    term: str = Field(
        default="",
        max_length=40,
        description="学期（可留空，多数情况能从原文里读到）",
    )


class AcademicImportAck(BaseModel):
    """导入回执：读到了什么、写进了哪两条画像摘要。"""

    model_config = ConfigDict(extra="forbid")

    school: str = ""
    source: str = ""
    term: str = ""
    courses: int = 0
    grades: int = 0
    imported_at: str = ""
    notes: list[str] = Field(default_factory=list)
    wrote_profile: list[str] = Field(default_factory=list)


class AcademicRevokeAck(BaseModel):
    """清空导入的回执。"""

    model_config = ConfigDict(extra="forbid")

    revoked: bool = Field(description="授权与取回的数据是否已经删掉")


class LayoutBlockView(BaseModel):
    """控制台上一个气泡的编排结果。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str = ""
    hint: str = ""
    weight: float = 1.0
    priority: int = 100
    why: str = Field(default="", description="排在这一位的原因，可直接显示给用户")


class IntelItemView(BaseModel):
    """一条外部情报。

    `source_url` 是这类信息的**依据**：说"这个岗位要 XX 能力"就得能点回原页面。
    没有来源的条目在服务层就被丢掉了，不会出现在这里。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str = Field(default="", description="机器可读的类别")
    kind_label: str = Field(default="", description="类别的中文名（界面显示它）")
    title: str = ""
    text: str = ""
    source_url: str = ""
    source_name: str = Field(default="", description="来源的中文称呼（界面显示它）")
    fetched_at: str = ""


class IntelListView(BaseModel):
    """外部情报清单。"""

    model_config = ConfigDict(extra="forbid")

    items: list[IntelItemView] = Field(default_factory=list)
    fetched_at: str = Field(default="", description="这一批的取回时间")


class WorkspacePageView(BaseModel):
    """工作台聚合视图。"""

    model_config = ConfigDict(extra="forbid")

    profile_panel: ProfilePanelView = Field(default_factory=ProfilePanelView)
    report_panel: Optional[StagePanelView] = Field(default=None, description="② 诊断与报告")
    plan_panel: Optional[StagePanelView] = Field(default=None, description="③ 方案")
    action_panel: Optional[StagePanelView] = Field(default=None, description="④ 计划与日历")
    review_panel: Optional[StagePanelView] = Field(default=None, description="⑤ 跟踪与预警")
    coach_messages: list[dict[str, Any]] = Field(
        default_factory=list, description="教练消息汇总"
    )
    dependencies: list[DependencyEdgeView] = Field(default_factory=list)
    collection_panel: CollectionPanelView = Field(
        default_factory=CollectionPanelView, description="采集动线（动态策略）"
    )
    academic_panel: Optional[AcademicPanelView] = Field(
        default=None,
        description="教务系统取回来的课表与成绩单；为 null 表示还没授权过",
    )
    layout_panel: list[LayoutBlockView] = Field(
        default_factory=list,
        description="气泡编排（已排序）：顺序、空间与出现条件来自动态资源",
    )
    axis_a_stage: Optional[str] = Field(
        default=None, description="轴 A 阶段过滤依据"
    )
