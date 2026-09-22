"""本地消息设施：内存事件总线 / 本地调度 / 本地通知。

第一期行为约定：
- InMemoryEventBus：进程内同步派发，注册顺序即调用顺序；订阅者异常必须隔离，
  因为"影响面传播""成就解锁"都是旁路，不能因为一个订阅者失败就断掉主链路；
- LocalScheduler：内存延迟队列 + 轮询，进程重启即丢失；
- LocalNotify：写本地消息表 + 打日志，不接真实推送。

替换点：自有事件总线 / 调度 / 通知。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from zhiyin_kernel.enums import NotifyChannel
from zhiyin_data_sdk.gateways.messaging import (
    EventBusGateway,
    EventHandler,
    NotifyGateway,
    NotifyResult,
    ScheduledTask,
    SchedulerGateway,
)
from zhiyin_infrastructure.local.repository import InMemoryNotificationRepository

logger = logging.getLogger(__name__)


class InMemoryEventBus(EventBusGateway):
    """进程内事件总线。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """派发给该类型的所有订阅者，单个订阅者失败只记日志不中断。"""
        for handler in list(self._handlers.get(event_type, ())):
            try:
                outcome = handler(payload)
                if inspect.isawaitable(outcome):
                    await outcome
            except Exception:
                logger.exception("事件订阅者处理失败：event_type=%s", event_type)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)


class LocalScheduler(SchedulerGateway):
    """本地调度器：内存延迟队列 + 轮询。

    到点后把 `ScheduledTask` 原样投递给事件总线（event_type + payload），
    由上层（编排层的 Scheduler）决定冷却期与触发次数上限这类策略。
    """

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(
        self,
        event_bus: Optional[EventBusGateway] = None,
        *,
        poll_interval_s: float = 1.0,
    ) -> None:
        self._event_bus = event_bus
        self._poll_interval_s = poll_interval_s
        self._tasks: dict[str, ScheduledTask] = {}
        self._next_run: dict[str, datetime] = {}
        self._poller: Optional[asyncio.Task[None]] = None

    def register(self, task: ScheduledTask) -> ScheduledTask:
        self._tasks[task.task_id] = task.model_copy(deep=True)
        if task.trigger_at is not None:
            self._next_run[task.task_id] = _as_utc(task.trigger_at)
        elif task.interval_s:
            self._next_run[task.task_id] = _now() + timedelta(seconds=task.interval_s)
        else:
            # 没给触发时间也不是周期任务，视为立即触发一次。
            self._next_run[task.task_id] = _now()
        return task

    def cancel(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._next_run.pop(task_id, None)

    def list_registered(self) -> list[ScheduledTask]:
        return [task.model_copy(deep=True) for task in self._tasks.values()]

    # ---------- 触发 ----------

    async def tick(self, now: Optional[datetime] = None) -> list[str]:
        """扫描到点任务并投递，返回到点触发的事件类型列表。

        显式暴露 tick 而不是只靠后台轮询，是为了让测试与本地演示可确定性复现。
        """
        moment = _as_utc(now) if now is not None else _now()
        fired: list[str] = []
        for task_id, due_at in list(self._next_run.items()):
            if due_at > moment:
                continue
            task = self._tasks.get(task_id)
            if task is None:
                self._next_run.pop(task_id, None)
                continue

            if self._event_bus is not None:
                # 带上触发时刻：上层（编排层的 Scheduler）要用它算冷却期。
                # 不传的话上层只能取接收时刻，冷却期在补偿/重放场景会算错。
                payload = {**task.payload, "occurred_at": moment.isoformat()}
                await self._event_bus.publish(task.event_type, payload)
            fired.append(task.event_type)

            if task.interval_s:
                self._next_run[task_id] = moment + timedelta(seconds=task.interval_s)
            else:
                # 一次性任务：触发后自动注销。
                self.cancel(task_id)
        return fired

    def start_polling(self) -> None:
        """启动后台轮询。"""
        if self._poller is not None and not self._poller.done():
            return
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
            except asyncio.CancelledError:
                raise
            except Exception:
                # 轮询任务一旦因为 tick() 抛错而退出，**之后再也不会有人唤醒它**：
                # 到期任务永久不再触发，而且没有任何日志（只有关停时才以
                # "Task exception was never retrieved" 的形式露一下）。
                # 与 postgres/scheduler.py 的 `_poll_forever` 保持同一口径：记日志继续跑。
                logger.exception("本地调度轮询失败，将在 %s 秒后重试", self._poll_interval_s)


class LocalNotify(NotifyGateway):
    """本地通知：写本地消息表 + 打日志。

    第一阶段不接真实通道，但保留"消息表"这一形态，方便复盘页与工作台读取教练消息。

    **写侧与读侧共用同一个存储**：本类把消息写进 `InMemoryNotificationRepository`，
    而 `FunctionService.list_pending_notifications` 与 `ActiveEventWorker` 的
    打扰度判定都从那个仓储读。此前两边各持一份（本类一个 list、读侧一个 dict），
    于是"通知发出去了，前端什么都读不到"—— 在 Postgres 模式下是同一个毛病
    （写 `orc_notification`、读进程内队列），现在两边都收口到同一处。
    """

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self, notifications: InMemoryNotificationRepository | None = None) -> None:
        # 不传就自己建一个：单测里 `LocalNotify()` 仍然自洽（写进去就能读出来）。
        self._notifications = notifications or InMemoryNotificationRepository()

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
        self._notifications.add(
            user_id,
            {
                "id": message_id,
                "user_id": user_id,
                "title": title,
                "body": body,
                "channel": channel.value,
                "action": action,
                "related_task_id": related_task_id,
                "occurred_at": _now().isoformat(),
            },
        )
        logger.info("本地通知：user=%s channel=%s title=%s", user_id, channel.value, title)
        return NotifyResult(message_id=message_id, channel=channel, delivered=True)

    def list_messages(self, user_id: str) -> list[dict[str, Any]]:
        """列出该用户的全部消息（含已读）。调试与单测用。"""
        return [dict(item) for item in self._notifications.store(user_id)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """统一为 UTC；naive 时间按 UTC 处理，避免与 _now() 比较时抛错。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["InMemoryEventBus", "LocalNotify", "LocalScheduler"]
