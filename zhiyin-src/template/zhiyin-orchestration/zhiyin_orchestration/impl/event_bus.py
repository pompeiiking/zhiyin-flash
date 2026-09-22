"""领域事件总线实现：把语义信封落到 EventBusGateway 上。"""

from __future__ import annotations

import asyncio
import inspect
from collections import deque
from typing import Any

from zhiyin_data_sdk.gateways.messaging import EventBusGateway
from zhiyin_orchestration.event import DomainEvent, EventBus, EventHandler
from zhiyin_orchestration.impl._shared import _coerce_event


class GatewayEventBus(EventBus):
    """把领域事件信封落到 EventBusGateway 上的实现。

    信封（DomainEvent）整体序列化进 payload，因此在切换实现时协议不变；
    消费方拿到的仍是完整信封，不需要回查状态。
    """

    def __init__(self, gateway: EventBusGateway, *, dedup_size: int = 1024) -> None:
        self._gateway = gateway
        self._handlers: dict[str, list[EventHandler]] = {}
        self._subscribed: set[str] = set()
        self._seen_keys: set[str] = set()
        self._seen_order: deque[str] = deque(maxlen=dedup_size)
        self._lock = asyncio.Lock()

    async def publish(self, event: DomainEvent) -> None:
        """发布事件。带 idempotency_key 时按 LRU 去重（R-ORC-007）。"""
        if event.idempotency_key is not None:
            async with self._lock:
                if event.idempotency_key in self._seen_keys:
                    return
                if (
                    self._seen_order.maxlen is not None
                    and len(self._seen_order) == self._seen_order.maxlen
                ):
                    self._seen_keys.discard(self._seen_order[0])
                self._seen_order.append(event.idempotency_key)
                self._seen_keys.add(event.idempotency_key)

        await self._gateway.publish(event.event_type, event.model_dump(mode="json"))

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅事件。同一事件可挂多个处理器，按注册顺序调用。"""
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(handler)
        if event_type not in self._subscribed:
            self._gateway.subscribe(event_type, self._make_dispatch(event_type))
            self._subscribed.add(event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """取消订阅。

        Gateway 契约不提供取消订阅，因此只摘掉本层的处理器；当某类型不再有任何
        处理器时，投递会被忽略。
        """
        handlers = self._handlers.get(event_type)
        if not handlers:
            return
        if handler in handlers:
            handlers.remove(handler)

    def _make_dispatch(self, event_type: str):
        async def _dispatch(payload: dict[str, Any]) -> None:
            event = _coerce_event(event_type, payload)
            if event.event_type != event_type:
                # 信封自带类型与订阅类型不一致时，以订阅类型为准，
                # 避免上游标错类型后订阅方集体收不到。
                event = event.model_copy(update={"event_type": event_type})
            for handler in list(self._handlers.get(event_type, ())):
                outcome = handler(event)
                if inspect.isawaitable(outcome):
                    await outcome

        return _dispatch


__all__ = ["GatewayEventBus"]
