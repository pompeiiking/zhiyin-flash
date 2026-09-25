"""九项页面 AI 任务的产出契约（对应前端 `src/ai/registry.ts`）。

口径：
- 字段与前端 TS 接口一一对齐，**前端不拼业务语义**：这里给出的 data / citations /
  rationale 就是前端渲染的全部输入；
- 本组模型同时是 agno `output_schema` 的落点（第六章 6.5）：
  Agent 的结构化产出校验到这些模型上，形状与前端契约一致；
- 来源标注、依据绑定和缓存由业务服务负责；缺少真实事实时不靠演示常量补位。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_business.contracts.common import Evidence


class Citation(BaseModel):
    """前端 AiCitation：产出必须与依据绑定。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    detail: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    at: str = ""
    origin: str = ""

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> "Citation":
        return cls(
            source=evidence.source or "画像字段",
            detail=evidence.detail or evidence.claim,
            confidence=0.8,
        )


class AiMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by: str = Field(description="主理智能体展示名，取 AgentRole 种子名")
    at: str = ""
    ms: int = 0
    cached: bool = False


class AiResultEnvelope(BaseModel):
    """SSE 终帧的 result 字段：{data, citations, meta, rationale}。"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    data: Any
    citations: list[Citation] = Field(default_factory=list)
    meta: AiMeta
    rationale: str = ""


# ---------------------------------------------------------------- 今日简报


class BriefNext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="输入中已登记的画像缺口键；无缺口时 next 必须为空")
    label: str
    why: str


class BriefToday(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    because: list[dict[str, str]] = Field(default_factory=list)  # {text, from}
    changed: list[dict[str, str]] = Field(default_factory=list)  # {text, at}
    if_you_skip: str = Field(default="", alias="ifYouSkip")
    next: list[BriefNext] = Field(default_factory=list)


# ---------------------------------------------------------------- 维度解读


class TrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    v: float
    why: str = ""


class DimensionReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    conclusion: str
    reading: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    delta: float | None = None
    bench: float | None = Field(default=None, description="有外部依据时的决策线 / 岗位要求基准")
    trend: list[TrendPoint] = Field(default_factory=list)
    next: str = ""


# ---------------------------------------------------------------- 缺口追问


class ClarifyOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    why: str = ""


class GapClarify(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    options: list[ClarifyOption] = Field(default_factory=list)
    why_now: str = Field(default="", alias="whyNow")


# ---------------------------------------------------------------- 对你的分析


class AnalysisPoint(BaseModel):
    """「对你的分析」里的一条：一句结论 + 它凭什么。"""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="这条叫什么，不超过 12 字")
    why: str = Field(default="", description="凭什么这么说，指回具体哪条记录")


class PortraitAnalysis(BaseModel):
    """「对你的分析」—— 画像第一屏的那段整体判断。

    为什么它必须是独立的一件产物：画像原本只有"字段 + 把握度"，
    那是一份**清单**。清单回答的是"记下了什么"，而用户问的是
    "这些合起来说明我现在是个什么处境" —— 后者要有人下判断。
    单条维度的解读（DimensionReading）补不上这一块：它一次只看一条字段，
    天然说不出"你手里有什么、缺什么、先动哪一件"。

    下判断的边界（和采集环节的分工）：这里可以判断**处境**（手里有什么、
    方向有多确定、卡在哪、下一步先做什么），但不给"你适合当 XX"这种
    职业结论 —— 那是诊断环节的事。
    """

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(description="一句话说清他现在的处境，不超过 30 字")
    reading: str = Field(description="2–4 段整体分析，段间用空行")
    strengths: list[AnalysisPoint] = Field(
        default_factory=list, description="他手里真的有的东西（资源 / 底子）"
    )
    watchouts: list[AnalysisPoint] = Field(
        default_factory=list, description="现在最该小心的"
    )
    next: list[AnalysisPoint] = Field(
        default_factory=list, description="接下来能做的事，动词开头"
    )


# ---------------------------------------------------------------- 报告结论


class DayAdvice(BaseModel):
    """「这一天的建议」—— 用户点开日历里的某一天时生成。

    为什么按天生成：日历上其余的部分都是**事实**（那天有哪几门课、哪个节点到期、
    哪件事该做完），事实读库读快照就有；用户缺的是"这一天我该怎么用"——
    哪一件最要紧、先动哪个、什么时候做。那是判断，要有人下。
    """

    model_config = ConfigDict(extra="forbid")

    date: str = Field(description="YYYY-MM-DD，原样回填用户点的那一天")
    headline: str = Field(description="一句话说清这一天最该被看见的是什么")
    reading: str = Field(description="2–3 句：这一天怎么过")
    plan: list[AnalysisPoint] = Field(
        default_factory=list, description="按时间排的 1–3 件，label 写清什么时候做什么"
    )
    watch: str = Field(default="", description="这天要小心的一件事；没有就留空")


# ---------------------------------------------------------------- 报告结论


class ReportMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    why: str


class ReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    paragraphs: list[str] = Field(default_factory=list)
    moves: list[ReportMove] = Field(default_factory=list)


# ---------------------------------------------------------------- 学信网绑定


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    teacher: str = ""
    day: int = Field(default=1, ge=1, le=7, description="1=周一 … 7=周日")
    start: int = Field(default=1, ge=1, le=12, description="起始节")
    span: int = Field(default=1, ge=1, description="连上节数")
    place: str = ""
    credit: float = 0.0
    # 空串是**如实**的一种取值：教务系统没写课程性质时，我们不该替他归到"必修"。
    # 界面照原样显示（空着），而不是显示一个我们自己编的类别。
    type: Literal["必修", "选修", "实践", ""] = ""
    score: Optional[float] = None
    why: str = ""
    supports: list[str] = Field(default_factory=list, description="撑起画像哪些维度")


class BindStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    detail: str
    got: int = 0
    source: str


class ProfileLift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dim: str
    from_value: float = Field(alias="from")
    to_value: float = Field(alias="to")
    because: str

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BindResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[BindStep]
    courses: list[Course] = Field(default_factory=list)
    lifted: list[ProfileLift] = Field(default_factory=list)


# ---------------------------------------------------------------- 课表


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str
    slot: str
    why: str


class PlanMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    what: str
    why: str


class TimetablePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    windows: list[TimeWindow] = Field(default_factory=list)
    moves: list[PlanMove] = Field(default_factory=list)


# ---------------------------------------------------------------- 待办建议


class TodoSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    why: str
    from_source: str = Field(alias="from")
    when: str = ""
    weight: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TodoSuggestions(BaseModel):
    """待办建议的**模型产出外壳**（对外仍然是一份数组）。

    为什么要包一层：结构化产出交给模型时，对象比顶层数组稳 ——
    顶层数组少一层字段名，模型容易漏掉包裹、或在数组前后补一句说明，
    而那样整轮产出就废了。服务层拿到之后取 `items` 再下发。
    """

    model_config = ConfigDict(extra="forbid")

    items: list[TodoSuggestion] = Field(default_factory=list)


# ---------------------------------------------------------------- 学职网匹配


class MatchCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track: str
    skill: str
    need: float
    have: float


class MatchRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track: str
    fit: float
    gap: str
    why: str


class MatchRecommend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    because: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cells: list[MatchCell] = Field(default_factory=list)
    ranking: list[MatchRanking] = Field(default_factory=list)
    recommend: MatchRecommend


__all__ = [
    "AiMeta",
    "AiResultEnvelope",
    "BindResult",
    "BindStep",
    "BriefNext",
    "BriefToday",
    "Citation",
    "ClarifyOption",
    "Course",
    "DimensionReading",
    "GapClarify",
    "MatchCell",
    "MatchRanking",
    "MatchRecommend",
    "MatchResult",
    "PlanMove",
    "ProfileLift",
    "ReportMove",
    "ReportSummary",
    "TimeWindow",
    "TimetablePlan",
    "TodoSuggestion",
    "TodoSuggestions",
    "TrendPoint",
]
