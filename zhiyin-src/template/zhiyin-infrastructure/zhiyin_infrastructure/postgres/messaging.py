"""PostgreSQL 事件总线与通知实现。"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Optional
from uuid import uuid4

from zhiyin_data_sdk.gateways.messaging import (
    EventBusGateway,
    EventHandler,
    NotifyGateway,
    NotifyResult,
)
from zhiyin_kernel.enums import NotifyChannel
from zhiyin_infrastructure.postgres.database import PostgresDatabase

logger = logging.getLogger(__name__)


class PostgresEventBus(EventBusGateway):
    """事件写入 outbox，同时派发给当前进程内的订阅者。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database
        self._handlers: dict[str, list[EventHandler]] = {}

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event_id = f"evt_{uuid4().hex[:16]}"
        await self._db.execute(
            """
            INSERT INTO orc_event_outbox (id, event_type, payload, status)
            VALUES ($1, $2, $3::jsonb, 'pending')
            """,
            event_id,
            event_type,
            json.dumps(payload, ensure_ascii=False),
        )
        for handler in list(self._handlers.get(event_type, ())):
            try:
                outcome = handler(payload)
                if inspect.isawaitable(outcome):
                    await outcome
            except Exception:
                logger.exception("事件订阅者处理失败：event_type=%s", event_type)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)


class PostgresNotifier(NotifyGateway):
    """通知写入 `orc_notification`。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

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
        message_id = f"msg_{uuid4().hex[:12]}"
        await self._db.execute(
            """
            INSERT INTO orc_notification
                (id, user_id, channel, status, title, body, action,
                 related_task_id, sent_at)
            VALUES ($1, $2, $3, 'sent', $4, $5, $6::jsonb, $7, NOW())
            """,
            message_id,
            user_id,
            channel.value,
            title,
            body,
            json.dumps(action, ensure_ascii=False) if action else None,
            related_task_id,
        )
        return NotifyResult(message_id=message_id, channel=channel, delivered=True)


__all__ = ["PostgresEventBus", "PostgresNotifier"]
