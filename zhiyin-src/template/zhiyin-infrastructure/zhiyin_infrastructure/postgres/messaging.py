"""PostgreSQL 事件总线与通知实现。"""

from __future__ import annotations

import asyncio
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
    """PostgreSQL outbox 事件总线。

    发布端只写数据库；订阅者由后台进程轮询投递。这样 API 多副本和
    `zhiyin-background` 不需要共享进程内队列，也不会把事件投给 API 中
    已经关闭的业务 Worker。

    领取使用 `available_at` 作为租约：消费者崩溃后事件会重新变得可领取。
    投递语义是 at-least-once，订阅者必须保持幂等。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        poll_interval_s: float = 1.0,
        batch_size: int = 100,
        lease_s: float = 30.0,
        retry_delay_s: float = 5.0,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError("outbox poll_interval_s 必须为正数")
        if batch_size < 1:
            raise ValueError("outbox batch_size 必须大于等于 1")
        if lease_s <= 0 or retry_delay_s <= 0:
            raise ValueError("outbox lease_s / retry_delay_s 必须为正数")
        self._db = database
        self._handlers: dict[str, list[EventHandler]] = {}
        self._poll_interval_s = poll_interval_s
        self._batch_size = batch_size
        self._lease_s = lease_s
        self._retry_delay_s = retry_delay_s
        self._poller: Optional[asyncio.Task[None]] = None

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """只写 outbox；跨进程投递统一由后台轮询完成。"""
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

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def poll_once(self) -> int:
        """领取并投递一批 outbox 事件，返回成功确认的事件数。"""
        rows = await self._claim_pending()
        published = 0
        for row in rows:
            event_id = str(row["id"])
            event_type = str(row["event_type"])
            payload = _load_json(row["payload"])
            try:
                for handler in list(self._handlers.get(event_type, ())):
                    outcome = handler(payload)
                    if inspect.isawaitable(outcome):
                        await outcome
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "outbox 事件投递失败，将延迟重试：id=%s event_type=%s",
                    event_id,
                    event_type,
                )
                await self._retry_later(event_id)
                continue

            await self._db.execute(
                """
                UPDATE orc_event_outbox
                SET status = 'published', published_at = NOW()
                WHERE id = $1 AND status = 'pending'
                """,
                event_id,
            )
            published += 1
        return published

    async def _claim_pending(self) -> list[Any]:
        """原子领取一批事件，并把下一次可领取时间推到租约之后。"""
        async with self._db.transaction() as connection:
            return await connection.fetch(
                """
                WITH claimed AS (
                    SELECT id
                    FROM orc_event_outbox
                    WHERE status = 'pending' AND available_at <= NOW()
                    ORDER BY available_at ASC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                )
                UPDATE orc_event_outbox AS event
                SET available_at = NOW() + ($2::double precision * INTERVAL '1 second')
                FROM claimed
                WHERE event.id = claimed.id
                RETURNING event.id, event.event_type, event.payload
                """,
                self._batch_size,
                self._lease_s,
            )

    async def _retry_later(self, event_id: str) -> None:
        await self._db.execute(
            """
            UPDATE orc_event_outbox
            SET available_at = NOW() + ($2::double precision * INTERVAL '1 second')
            WHERE id = $1 AND status = 'pending'
            """,
            event_id,
            self._retry_delay_s,
        )

    def start_polling(self) -> None:
        """启动 outbox 后台轮询；重复调用不重复创建任务。"""
        if self._poller is not None and not self._poller.done():
            return
        self._poller = asyncio.get_running_loop().create_task(self._poll_forever())

    async def stop_polling(self) -> None:
        if self._poller is None:
            return
        self._poller.cancel()
        try:
            await self._poller
        except asyncio.CancelledError:
            pass
        self._poller = None

    async def _poll_forever(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("PostgreSQL outbox 轮询失败")
            await asyncio.sleep(self._poll_interval_s)

    async def aclose(self) -> None:
        await self.stop_polling()


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


def _load_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


__all__ = ["PostgresEventBus", "PostgresNotifier"]
