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


class PlanPatch(BaseModel):
    """复盘对行动计划的**结构化**调整。

    实测（ZY-05）：复盘里明确说"周六上午删掉、只用周二周四"，而行动计划里那三条
    周六任务一条都没少 —— 话改了、资产没改，用户第二天看到的仍是旧计划。

    只做「删」与「挪」：新增任务属于 ④ 行动环节的产出，复盘不越界造任务。
    命中的写法：任务 id 精确相等，或关键词出现在任务文本里（复盘说的是人话，不是 id）。
    """

    model_config = ConfigDict(extra="forbid")

    drop_tasks: list[str] = Field(
        default_factory=list,
        description="要删掉的任务：写任务 id，或写能识别它的文本关键词（如「周六」）",
    )
    reschedule_tasks: dict[str, str] = Field(
        default_factory=dict,
        description="任务 id 或文本关键词 → 新的截止时间（ISO 日期，如 2026-10-17）",
    )
    reschedule_phases: dict[str, str] = Field(
        default_factory=dict,
        description="阶段名 → 新的 date_range（如「10-15 ~ 10-21」）",
    )
    reason: str = Field(default="", description="为什么这样调整，一句话")


class ReviewOutput(BaseModel):
    """⑤ 复盘校准的产出契约。"""

    model_config = ConfigDict(extra="forbid")

    conclusion: str = Field(
        default="",
        description=(
            "这一轮对他说的话：2 到 4 句，每句不超过 40 字。先说清你看见的是什么"
            "（具体到那件事），再说这一轮把力气放在哪。不施压、不追究。"
            "**不要**写成「我为什么要问他这个」这类场外话。"
        )
    )
    attribution: ReviewAttribution = Field(description="归因判别结论")
    progress: ProgressSnapshot = Field(default_factory=ProgressSnapshot)
    minimal_action: GuideTask = Field(
        description="最小可执行动作，必须立即能勾掉"
    )
    plan_patch: Optional[PlanPatch] = Field(
        default=None,
        description=(
            "本轮复盘改变了时间安排或任务取舍时给出；只是回话、不动计划就留 null。"
            "**口头说了要改而这里不写，计划就不会变** —— 那正是用户第二天看到的旧计划。"
        ),
    )
    next_handoff_stage: Optional[LoopStage] = Field(
        default=None,
        description="方向动摇时交职业顾问增量重算 ②③；任务太大时交路径规划师重拆",
    )
    achievements_unlocked: list[str] = Field(
        default_factory=list, description="本次解锁的成就 badge_key（只由行为日志驱动）"
    )
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    guide: BehaviorGuide | None = Field(
        default=None,
        description="下一步：让用户做一次小行动 → 再入环。没想好就给 null",
    )
    disclosure: Disclosure | None = None
