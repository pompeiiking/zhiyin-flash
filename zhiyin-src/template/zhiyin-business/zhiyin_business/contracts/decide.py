"""③ 决策产出契约。

验收锚点：给"可撤回的选择 + 依据"，不给"唯一正确答案"。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import PlanRole
from zhiyin_business.contracts.common import (
    BehaviorGuide,
    Disclosure,
    TheoryRef,
)


class PlanOption(BaseModel):
    """单套方案结构。"""

    model_config = ConfigDict(extra="forbid")

    option_id: str
    role: PlanRole
    name: str
    target_desc: str
    match_score: float = Field(
        description="匹配度 = 三叶草契合度 × 可达性，解释性分值"
    )
    gaps: list[str] = Field(default_factory=list, description="该方向下的差距要点")
    fit_reason: str = Field(description="契合依据")
    main_risk: str = Field(description="主要风险")
    theory_refs: list[TheoryRef] = Field(default_factory=list)


class DecideOutput(BaseModel):
    """③ 决策的产出契约。"""

    model_config = ConfigDict(extra="forbid")

    plans: list[PlanOption] = Field(
        default_factory=list, description="主攻 / 平行 / 保底 三套"
    )
    match_score_method: str = Field(
        default="三叶草契合度 × 可达性", description="匹配度口径说明，必须对用户可见"
    )
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    guide: BehaviorGuide = Field(description="下一步：让用户做出可撤回的选择")
    disclosure: Disclosure | None = None
