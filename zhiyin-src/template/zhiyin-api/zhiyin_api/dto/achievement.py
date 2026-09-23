"""完成记录（成就）的对外形状。

为什么单独一个模块而不是塞进 workspace：这一屏读的是**行为日志的推导结果**，
不是工作台那几个聚合面板的一部分 —— 它有自己的取数路径（见
`FunctionService.list_achievements`），前端也是一块独立的界面。

名字口径：内部说"成就"，界面上说「完成记录」（见设计文档 7.3 的内部词对照）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AchievementView(BaseModel):
    """一枚完成记录。

    只有三样东西：它是哪一枚、拿到没有、什么时候拿到的。
    **没有进度条、没有百分比** —— 这类记录的解锁条件是"做过一次某件事"，
    拆成进度就是编出来的刻度（"认领差距 60%"没有含义）。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="规则 code；文案由前端按 `badge.<key>` 从文案包取")
    unlocked: bool = False
    unlocked_at: Optional[datetime] = Field(
        default=None, description="第一次做到那件事的时间（未解锁为 null）"
    )


class AchievementListView(BaseModel):
    """整屏完成的记录：全部规则 + 其中拿到几枚。"""

    model_config = ConfigDict(extra="forbid")

    items: list[AchievementView] = Field(default_factory=list)
    unlocked: int = 0
    total: int = 0


__all__ = ["AchievementListView", "AchievementView"]
