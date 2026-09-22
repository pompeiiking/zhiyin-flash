"""PostgreSQL 调度器实现。

契约里的 register / cancel 是同步方法，因此本实现维护进程内缓存并异步落库；
轮询与到点投递从 `orc_schedule_job` 读取，重启后任务仍在。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from zhiyin_data_sdk.gateways.messaging import (
    EventBusGateway,
    ScheduledTask,
    SchedulerGateway,
)
from zhiyin_infrastructure.postgres.database import PostgresDatabase

logger = logging.getLogger(__name__)


class PostgresScheduler(SchedulerGateway):
    """持久化调度器。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        database: PostgresDatabase,
        event_bus: Optional[EventBusGateway] = None,
        *,
        poll_interval_s: float = 1.0,
    ) -> None:
        self._db = database
        self._event_bus = event_bus
        self._poll_interval_s = poll_interval_s
        self._tasks: dict[str, ScheduledTask] = {}
        self._poller: Optional[asyncio.Task[None]] = None
        self._pending: list[Any] = []
        self._write_tasks: set[asyncio.Task[Any]] = set()

    def register(self, task: ScheduledTask) -> ScheduledTask:
        self._tasks[task.task_id] = task.model_copy(deep=True)
        self._spawn(self._upsert(task))
        return task

    def cancel(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._spawn(self._delete(task_id))

    def list_registered(self) -> list[ScheduledTask]:
        return [task.model_copy(deep=True) for task in self._tasks.values()]

    async def tick(self, now: Optional[datetime] = None) -> list[str]:
        moment = _as_utc(now) if now is not None else _now()
        rows = await self._db.fetch(
            """
            SELECT id, payload
            FROM orc_schedule_job
            WHERE status = 'pending' AND run_at <= $1
            ORDER BY run_at ASC
            """,
            moment,
        )
        fired: list[str] = []
        for row in rows:
            raw = _load_json(row["payload"])
            task = ScheduledTask.model_validate(raw.get("task") or {})
            if self._event_bus is not None:
                await self._event_bus.publish(
                    task.event_type,
                    {**task.payload, "occurred_at": moment.isoformat()},
                )
            fired.append(task.event_type)
            if task.interval_s:
                await self._db.execute(
                    """
                    UPDATE orc_schedule_job
                    SET run_at = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    task.task_id,
                    moment + timedelta(seconds=task.interval_s),
                )
            else:
                self._tasks.pop(task.task_id, None)
                await self._db.execute(
                    """
                    UPDATE orc_schedule_job
                    SET status = 'done', updated_at = NOW()
                    WHERE id = $1
                    """,
                    task.task_id,
                )
        return fired

    def start_polling(self) -> None:
        if self._poller is not None and not self._poller.done():
            return
        for coro in self._pending:
            self._track(asyncio.get_event_loop().create_task(coro))
        self._pending.clear()
        self._poller = asyncio.get_event_loop().create_task(self._poll_forever())

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
            await asyncio.sleep(self._poll_interval_s)
            try:
                await self.tick()
            except Exception:
                logger.exception("PostgresScheduler tick 失败")

    async def _upsert(self, task: ScheduledTask) -> None:
        run_at = _next_run(task)
        try:
            await self._db.execute(
                """
                INSERT INTO orc_schedule_job
                    (id, job_type, run_at, status, payload, updated_at)
                VALUES ($1, $2, $3, 'pending', $4::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    job_type = EXCLUDED.job_type,
                    run_at = EXCLUDED.run_at,
                    status = 'pending',
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                task.task_id,
                task.event_type,
                run_at,
                json.dumps({"task": task.model_dump(mode="json")}, ensure_ascii=False),
            )
        except Exception:
            logger.exception("调度任务落库失败：%s", task.task_id)

    async def _delete(self, task_id: str) -> None:
        try:
            await self._db.execute(
                "DELETE FROM orc_schedule_job WHERE id = $1", task_id
            )
        except Exception:
            logger.exception("调度任务删除失败：%s", task_id)

    def _spawn(self, coro: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._pending.append(coro)
            return
        self._track(loop.create_task(coro))

    def _track(self, task: asyncio.Task[Any]) -> None:
        self._write_tasks.add(task)
        task.add_done_callback(self._write_tasks.discard)


def _next_run(task: ScheduledTask) -> datetime:
    if task.trigger_at is not None:
        return _as_utc(task.trigger_at)
    if task.interval_s:
        return _now() + timedelta(seconds=task.interval_s)
    return _now()


def _load_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["PostgresScheduler"]
