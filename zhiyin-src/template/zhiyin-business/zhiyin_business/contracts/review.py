"""⑤ 复盘校准产出契约。

验收锚点：只由真实行为信号触发，不允许系统自嗨式打扰；
教练消息必须带一个最小可执行动作，基调鼓励而非施压。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import LoopStage, ReviewAttribution
from zhiyin_business.contracts.common import (
    BehaviorGuide,
    Disclosure,
    GuideTask,
    TheoryRef,
)


class ProgressSnapshot(BaseModel):
    """进度快照。复盘产出的客观面。"""

    model_config = ConfigDict(extra="forbid")

    stages_visited: list[LoopStage] = Field(default_factory=list)
    tasks_done: int = 0
    tasks_total: int = 0
    days_inactive: int = 0
    last_behavior_at: Optional[str] = None


class ReviewOutput(BaseModel):
    """⑤ 复盘校准的产出契约。"""

    model_config = ConfigDict(extra="forbid")

    attribution: ReviewAttribution = Field(description="归因判别结论")
    progress: ProgressSnapshot = Field(default_factory=ProgressSnapshot)
    minimal_action: GuideTask = Field(
        description="最小可执行动作，必须立即能勾掉"
    )
    next_handoff_stage: Optional[LoopStage] = Field(
        default=None,
        description="方向动摇时交职业顾问增量重算 ②③；任务太大时交路径规划师重拆",
    )
    achievements_unlocked: list[str] = Field(
        default_factory=list, description="本次解锁的成就 badge_key（只由行为日志驱动）"
    )
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    guide: BehaviorGuide = Field(description="下一步：让用户做一次小行动 → 再入环")
    disclosure: Disclosure | None = None
