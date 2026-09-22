"""事件 / 调度 / 通知 Gateway。

第一期默认实现（见 zhiyin-infrastructure）：
- EventBusGateway  → InMemoryEventBus（进程内派发）
- SchedulerGateway → LocalScheduler（内存延迟队列 + 轮询）
- NotifyGateway    → LocalNotify（写本地消息表 + 打日志）

TODO：按自有基础设施演进。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import NotifyChannel

EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class EventBusGateway(ABC):
    """事件总线 Port。

    注：本层只处理"事件字典"，不理解事件语义；业务语义在业务层 events 模块。
    """

    @abstractmethod
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """发布事件。"""

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅事件。同一事件可多个订阅者。"""


class ScheduledTask(BaseModel):
    """一个被注册的调度任务。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    event_type: str = Field(description="触发时发布的事件类型")
    payload: dict[str, Any] = Field(default_factory=dict)
    trigger_at: Optional[datetime] = Field(default=None, description="定点触发")
    interval_s: Optional[float] = Field(default=None, description="周期触发间隔（秒）")
    owner_id: Optional[str] = Field(default=None, description="归属用户，如停滞检测")


class SchedulerGateway(ABC):
    """调度 Port。承载主动事件（教练提醒 / 节点到期 / 停滞超时）。"""

    @abstractmethod
    def register(self, task: ScheduledTask) -> ScheduledTask:
        """注册调度任务。"""

    @abstractmethod
    def cancel(self, task_id: str) -> None:
        """取消调度任务。"""

    @abstractmethod
    def list_registered(self) -> list[ScheduledTask]:
        """列出已注册任务。用于本地调试与演示。"""


class NotifyResult(BaseModel):
    """通知结果。"""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    channel: NotifyChannel
    delivered: bool = False


class NotifyGateway(ABC):
    """通知 Port。第一期只有本地通道，不接真实短信 / 推送。"""

    @abstractmethod
    async def push(
        self,
        user_id: str,
        *,
        title: str,
        body: str,
        channel: NotifyChannel = NotifyChannel.IN_APP,
        action: Optional[dict[str, Any]] = None,
        related_task_id: Optional[str] = None,
    ) -> NotifyResult:
        """推送一条通知。"""
