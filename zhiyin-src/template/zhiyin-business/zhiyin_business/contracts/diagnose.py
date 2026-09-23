"""② 诊断匹配产出契约。

验收锚点：产出必须收敛到"用户认领差距"，不能停在"我帮你分析完了"。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.assets import (
    ReportDimensionGroup,
    Swot,
    Verdict,
)
from zhiyin_business.contracts.common import (
    BehaviorGuide,
    Disclosure,
    Evidence,
    TheoryRef,
)


class DiagnoseGap(BaseModel):
    """差距清单条目：要求 − 现状 = 差距 + 补齐建议。"""

    model_config = ConfigDict(extra="forbid")

    gap_id: str
    requirement: str
    current_state: str
    suggestion: str
    theory_refs: list[TheoryRef] = Field(default_factory=list)


class FactItem(BaseModel):
    """信息侦查员供的事实。不进入对话主线闲聊。"""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="如 岗位要求 / 行业行情 / 时间窗口")
    content: str
    source: str = Field(default="", description="来源，如 学职平台 / JD")
    fetched_at: str = ""


class DiagnoseOutput(BaseModel):
    """② 诊断匹配的产出契约。"""

    model_config = ConfigDict(extra="forbid")

    conclusion: str = Field(
        default="",
        description=(
            "这一轮对他说的话：2 到 4 句，每句不超过 40 字。用人话把 verdict 那句结论说给他听，"
            "并说清凭什么这么判断（指到他的项目、材料、时间或外面那条真实要求）——"
            "verdict 进报告，conclusion 进对话。"
        )
    )
    verdict: Verdict
    swot: Swot
    dimensions: list[ReportDimensionGroup] = Field(
        default_factory=list, description="15 维：自我画像 6 / 职业环境 5 / 决策与风险 4"
    )
    gaps: list[DiagnoseGap] = Field(default_factory=list)
    facts: list[FactItem] = Field(default_factory=list, description="信息侦查员供数")
    evidences: list[Evidence] = Field(default_factory=list)
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    confidence_used: float = Field(
        default=0.0, description="本次诊断所用的画像置信度；不足时应回 ① 采集"
    )
    guide: BehaviorGuide | None = Field(
        default=None,
        description=(
            "下一步：引导认领差距。**可以不给** —— 没想好合适的选项就给 null，"
            "系统会用你写的结论收尾"
        ),
    )
    disclosure: Disclosure | None = None
