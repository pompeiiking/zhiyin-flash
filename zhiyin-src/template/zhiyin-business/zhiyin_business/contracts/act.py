"""④ 行动产出契约。

验收锚点：任务是"今天/本周勾得掉"的粒度；拆不动就回 ② 检查方向问题，不硬拆。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.assets import ActionPhase
from zhiyin_business.contracts.common import (
    BehaviorGuide,
    Disclosure,
    TheoryRef,
)


class NodeReminder(BaseModel):
    """关键节点提醒（入口）。第一期只登记，不做真实推送。"""

    model_config = ConfigDict(extra="forbid")

    title: str
    due_at: Optional[datetime] = None
    related_task_text: str = ""
    calendar_synced: bool = Field(
        default=False, description="是否已写入关键节点日历（规划师写入、教练读取）"
    )


class ActOutput(BaseModel):
    """④ 行动的产出契约。"""

    model_config = ConfigDict(extra="forbid")

    phases: list[ActionPhase] = Field(default_factory=list, description="阶段里程碑与任务")
    reminders: list[NodeReminder] = Field(default_factory=list)
    calendar_used: str = Field(
        default="general_template",
        description="计划依据：关键节点日历 / 通用节奏模板",
    )
    need_recheck_direction: bool = Field(
        default=False, description="任务拆不动时为 True，应回 ② 而非硬拆"
    )
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    guide: BehaviorGuide = Field(description="下一步：让用户勾掉第一个小任务")
    disclosure: Disclosure | None = None
