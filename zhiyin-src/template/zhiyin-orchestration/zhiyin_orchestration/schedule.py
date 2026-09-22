"""Scheduler 原语：定时、延迟与主动事件触发。

**契约分工**：本模块是语义契约（业务侧注册"停滞检测"等真实信号任务，并声明
冷却期与触发次数上限）；到点投递动作由 zhiyin-data-sdk 的 `SchedulerGateway`
承担（当前 LocalScheduler）。
第一期默认实现见 `zhiyin_orchestration.impl.GatewayScheduler`。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScheduleSpec(BaseModel):
    """调度注册项。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    event_type: str = Field(description="触发时发布的事件类型")
    payload: dict[str, Any] = Field(default_factory=dict)
    trigger_at: Optional[datetime] = None
    interval_s: Optional[float] = None
    cooldown_s: Optional[float] = Field(
        default=None, description="冷却期；用于打扰度控制"
    )
    max_triggers: Optional[int] = Field(default=None, description="打扰度上限")


class Scheduler(ABC):
    """调度器 Port。"""

    @abstractmethod
    def register(self, spec: ScheduleSpec) -> ScheduleSpec:
        """注册调度项。"""

    @abstractmethod
    def cancel(self, task_id: str) -> None:
        """取消调度项。"""

    @abstractmethod
    def list_registered(self) -> list[ScheduleSpec]:
        """列出已注册项。"""
