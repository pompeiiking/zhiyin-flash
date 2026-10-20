"""智能工作台 DTO（按 ①-⑤ 分层聚合）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_api.dto.common import TheoryRefView
from zhiyin_kernel.enums import (
    LoopStage,
    ProfileClueStatus,
    ProfileEntryStatus,
    ProfileEntryType,
    ProfileSource,
    ProfileVerification,
)


class ProfileFieldView(BaseModel):
    """画像里的一条记录（活状态的最小单位）。

    此前这里是 `dict[str, Any]`：契约只说"有 fields"，不说每条里有什么。
    前端要按 `confidence` 画把握度、按 `evidence` 做可溯源展示、按 `source`
    说明这条从哪来 —— 全是猜的字段名。现在逐字段声明。

    《个人画像设计-2026-10-20》第 4 节：一条记录还要能回答「属于哪一类内容、
    结构是什么、原话在哪、核实到什么程度、何时仍适用」。这些字段都来自服务端
    词表与写入校验，前端只按它们组织展示，不再自己猜键的含义。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="字段键，如 major / skills / interest（取数用，不直接展示）")
    label: str = Field(
        default="",
        description="字段的展示名（来自动态资源）；为空表示这份配置里没有它，界面回落到 key",
    )
    value: Any = Field(default=None, description="字段值，结构由画像 schema 决定")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="兼容字段，界面不再展示成百分比")
    source: ProfileSource
    updated_at: datetime
    evidence: list[str] = Field(default_factory=list, description="证据来源引用")
    #: 内容类别（学习背景/兴趣/经历/能力/职业关注/价值取向/现实条件/补充信息）。
    entry_type: ProfileEntryType = Field(default=ProfileEntryType.SUPPLEMENT)
    entry_type_label: str = Field(default="", description="内容类别的中文名（界面显示它）")
    #: 类别专属结构化属性（兴趣的正负与情境、职业关注的关注状态、能力的证据类型等）。
    attributes: dict[str, Any] = Field(default_factory=dict)
    #: 核实状态：与来源分开表达，不用一个分数混合。
    verification: ProfileVerification = Field(default=ProfileVerification.PENDING)
    verification_label: str = Field(default="", description="核实状态的中文名（界面显示它）")
    status: ProfileEntryStatus = Field(default=ProfileEntryStatus.ACTIVE)
    origin_ref: str = Field(default="", description="原话或资料来源引用")
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    event_at: Optional[datetime] = None
    entry_version: int = Field(default=1, ge=1)
    superseded_by: str = Field(default="")


class ProfileFieldUpdateRequest(BaseModel):
    """用户手动更正一条画像字段（issue #26 第三条）。

    只有一个 `value`，键在路径上（`POST /app/profile/fields/{key}`）：
    "改哪一条"不是可选的 —— 揉进请求体里，就等于允许一次请求改任意多条，
    而界面上的入口从来只对着一条。

    **为什么这里不设长度上限**：上限是业务口径（40 字，见
    `DefaultProfileService.MAX_FIELD_VALUE_CHARS`），超长要说人话
    （"最多 40 个字，现在有 56 个"）。交给 Pydantic 的 `max_length` 只会得到
    一句英文的字段名错误，用户看不懂自己该改什么。
    """

    model_config = ConfigDict(extra="forbid")

    value: str = Field(description="用户认可的那个值（空串会被拒 —— 清空是另一件事）")
    expected_updated_at: datetime | None = Field(
        default=None, description="编辑时字段时间；首次填写传 null"
    )


class ProfileConflictResolveRequest(BaseModel):
    """用户裁定一条冲突：以新说法为准，或保留当前记录。"""

    model_config = ConfigDict(extra="forbid")

    choice: str = Field(description="revision=以这条说法为准；current=保留当前记录")


class ProfileConflictView(BaseModel):
    """历史版本 / 冲突提案（设计第 7 节）。

    与 `ProfileFieldView` 分开：它不是当前事实，不能混进用途读取；
    界面用它展示「另一种说法」并让用户裁定。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    key: str
    label: str = ""
    value: Any = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: ProfileSource
    verification: ProfileVerification = ProfileVerification.PENDING
    verification_label: str = ""
    status: ProfileEntryStatus = ProfileEntryStatus.CONFLICT
    status_label: str = ""
    evidence: list[str] = Field(default_factory=list)
    origin_ref: str = ""
    created_at: datetime
    replaced_at: Optional[datetime] = None
    change_reason: str = ""


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


class ProfileClueView(BaseModel):
    """一条待验证线索（《个人画像设计-2026-10-20》第 3.2、9 节）。

    它是「系统基于证据的理解」，不是用户说过的事实 —— 所以单独一个形状、
    单独一组展示，并且带 `status` 与 `invalidated_reason`：被更正/删除依据或
    被用户否认之后，界面要能说清这条为什么不再算数，而不是让它悄悄消失。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str = Field(description="线索正文：一句「可能……」的有限理解")
    evidence: list[str] = Field(default_factory=list, description="依据引用")
    field_keys: list[str] = Field(
        default_factory=list, description="依据哪些画像字段；这些字段变更时线索失效"
    )
    status: ProfileClueStatus = Field(default=ProfileClueStatus.PROPOSED)
    invalidated_reason: str = Field(default="", description="为什么失效（给用户看的一句话）")
    created_at: datetime
    updated_at: datetime


class ProfileClueDenyAck(BaseModel):
    """否认一条「系统理解」的回执。"""

    model_config = ConfigDict(extra="forbid")

    denied: str = Field(description="已否认的那条线索 id")


class ProfileFieldDeleteAck(BaseModel):
    """用户删除一条画像信息的回执。"""

    model_config = ConfigDict(extra="forbid")

    deleted: str = Field(description="已删除的画像字段键")


class ProfilePanelView(BaseModel):
    """① 画像状态：字段覆盖度 / 置信度 / 缺口 / 更新时间。"""

    model_config = ConfigDict(extra="forbid")

    coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="字段覆盖度")
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fields: list[ProfileFieldView] = Field(default_factory=list)
    gaps: list[ProfileGapView] = Field(default_factory=list)
    clues: list[ProfileClueView] = Field(
        default_factory=list,
        description="系统基于证据的理解（待验证线索）：与 fields 分开，可否认",
    )
    conflicts: list[ProfileConflictView] = Field(
        default_factory=list,
        description="与当前记录不一致的另一种说法：并存等待用户裁定，不参与用途读取",
    )
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
    ask: str = Field(
        default="",
        description=(
            "问用户的那一句（只有 conversation 源、且还没拿到时有）；"
            "界面点「去回答」就把它带进对话，不为空表示这一条有可直接执行的动作"
        ),
    )


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
    courses_scheduled: int = Field(
        default=0,
        description=(
            "读出了上课时间的课数。`courses` 是「进了库」，它是「排进了课表」——"
            "界面必须分别说，否则用户看到「导入完成」却查不到课。"
        ),
    )
    grades: int = 0
    imported_at: str = ""
    notes: list[str] = Field(default_factory=list)
    wrote_profile: list[str] = Field(default_factory=list)


class AcademicImportUpload(BaseModel):
    """上传导入的载荷：两份文件（字节）+ 同一栏里可选的粘贴文本。

    为什么字节也放在 DTO 里：它是**内部载荷**（只在 `facade` 与业务服务之间传），
    不出现在任何路由签名里，因此不会进契约快照。用同一个形状承载"文件或文本"，
    是为了让业务层看到的是"一次导入要读什么"，而不是八个散着的参数。
    """

    model_config = ConfigDict(extra="forbid")

    courses_file: Optional[bytes] = None
    grades_file: Optional[bytes] = None
    courses_name: str = Field(default="", description="文件名，只用于出错时点名（「xx.json」）")
    grades_name: str = ""
    courses_text: str = Field(default="", max_length=200_000, description="同一栏里粘贴的原文")
    grades_text: str = Field(default="", max_length=200_000)
    school: str = Field(default="", max_length=120)
    term: str = Field(default="", max_length=40)


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
    #: direction = 按当前方向方案取回；major = 专业对口参考。
    relation: str = ""


class IntelListView(BaseModel):
    """外部情报清单。"""

    model_config = ConfigDict(extra="forbid")

    items: list[IntelItemView] = Field(default_factory=list)
    fetched_at: str = Field(default="", description="这一批的取回时间")
    #: 取数状态：ok / empty / failed / unknown —— 学生要能区分"确实没有"
    #: 与"这次没取到，可以重试"，而不是把失败当成 0 条。
    status: str = ""
    message: str = Field(default="", description="给学生看的下一步说明")
    #: 画像里已记录的专业（"专业起点"的依据，不受本次取数成败影响）。
    major: str = ""
    #: 本次探索实际依据：方向方案名或专业名；空串 = 还没有可用依据。
    basis: str = ""
    #: basis 的类型：direction（方向方案）/ profile（画像专业）/ 空。
    basis_kind: str = ""
    #: 专业/职业/案例分别几条（《个人画像设计》第 8 节：不能只报一个总数）。
    counts: dict[str, int] = Field(default_factory=dict)
    #: 本次实际下发的检索词（专业词 / 职业关注词）：可回看的取数依据。
    query: dict[str, list[str]] = Field(default_factory=dict)
    #: 职业条目的取得方式：官方专业映射 / 名称检索各几条。
    occupation_sources: dict[str, int] = Field(default_factory=dict)


class CapabilityItemView(BaseModel):
    """一项对话/业务能力在**当前部署**是否可用。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    available: bool = False
    reason: str = Field(default="", description="不可用原因（给学生看的）")
    fallback: str = Field(default="", description="不可用时的替代做法")


class CapabilityListView(BaseModel):
    """能力自检清单：前端能力面板与服务端真实配置同源。"""

    model_config = ConfigDict(extra="forbid")

    items: list[CapabilityItemView] = Field(default_factory=list)
    generated_at: str = ""


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
