"""EventBus 原语：领域事件发布 / 订阅 / 幂等消费。

**契约分工（避免与 SDK 重复定义）**：
- 本模块是**语义契约**，业务层只面向它编程：收发的是带信封的 DomainEvent
  （event_id / occurred_at / idempotency_key），因此幂等和追溯由本层保证。
- 传输由 zhiyin-data-sdk 的 `EventBusGateway` 承担，第一期实现为
  InMemoryEventBus（进程内派发），后续换实现时本层与业务层都不改动。
- 第一期默认实现见 `zhiyin_orchestration.impl.GatewayEventBus`。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

EventHandler = Callable[["DomainEvent"], Awaitable[None] | None]


class DomainEvent(BaseModel):
    """领域事件信封。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str = Field(description="事件类型字符串，取值由业务层定义")
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(
        default=None, description="幂等键；重复投递时消费方据此去重"
    )


class EventBus(ABC):
    """事件总线 Port。"""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """发布事件。"""

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅事件。"""

    @abstractmethod
    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """取消订阅。"""
