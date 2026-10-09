"""Worker 驱动：把"跑一轮"变成"一直跑 / 随生命周期跑"。

为什么驱动逻辑在装配层，而不在 Worker 基类里
--------------------------------------------
Worker 契约（`zhiyin_kernel.worker.Worker`）只有 `name` 与 `run_once`——
因为它必须被**业务层与基础设施层同时**依赖，而这两层唯一的公共依赖是内核，
内核又不允许出现行为（asyncio 循环属于行为）。

于是分工变成：

- 谁需要知道"该跑了" → 只有装配层（boot 允许 import 全部层）；
- Worker 自己只管"跑一轮做什么"。

这样换启动方式（同进程 lifespan / 独立进程 / 未来 Kubernetes CronJob）只改本文件，
Worker 实现与契约都不动。
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import signal
from typing import Protocol

logger = logging.getLogger(__name__)


class Runnable(Protocol):
    """驱动方需要的最小形状（鸭子类型）。

    用 Protocol 而不是继承抽象类：驱动方不应该反过来要求 Worker 继承什么，
    只要它有 `name` 与 `run_once` 就能被驱动。
    """

    name: str

    async def run_once(self) -> int:  # pragma: no cover - 协议声明
        ...


async def run_forever(worker: Runnable, interval_s: float) -> None:
    """按固定间隔轮询，直到被取消。"""
    if interval_s <= 0:
        raise ValueError("interval_s 必须为正数")
    while True:
        try:
            await worker.run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Worker %s 单轮执行失败，将在 %s 秒后继续重试",
                getattr(worker, "name", type(worker).__name__),
                interval_s,
            )
        await asyncio.sleep(interval_s)


async def run_until_cancelled(
    worker: Runnable, interval_s: float, stop: asyncio.Event
) -> None:
    """在 `stop` 被设置前轮询；用于 lifespan 内的统一启停。"""
    task = asyncio.create_task(run_forever(worker, interval_s))
    try:
        # 与"驱动任务自己挂掉"竞速：只等 stop 的话，run_forever 在运行期抛出
        # （例如 interval_s <= 0）会被 task 静默持有，调用方永远等在一个
        # 不会再有进展的 stop 上。谁先完成谁说话。
        stop_task = asyncio.ensure_future(stop.wait())
        done, _pending = await asyncio.wait(
            {task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            # 驱动方自己结束了：把它的异常原样抛出（CancelledError 也照抛）
            stop_task.cancel()
            await task
        stop_task.cancel()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def run_background_container(container) -> None:  # noqa: ANN001
    """在一个独立进程中运行调度器与全部后台 Worker。

    API 多副本时它们不再随每个 ASGI lifespan 重复启动，而是由
    Compose 中固定单副本的 `zhiyin-background` 调用这个入口。
    """
    from zhiyin_business.services.dynamic_config import load_snapshot

    if container.registry_service is not None:
        await load_snapshot(container.registry_service)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
            installed_signals.append(signum)
        except (NotImplementedError, RuntimeError):
            # Windows Proactor loop 不支持 add_signal_handler；Ctrl+C 仍会由
            # asyncio.run 取消主任务，下面的 finally 照样清理。
            pass

    event_bus = container.event_bus
    start_event_polling = getattr(event_bus, "start_polling", None)
    if callable(start_event_polling):
        start_event_polling()

    scheduler = container.scheduler
    start_polling = getattr(scheduler, "start_polling", None)
    if callable(start_polling):
        start_polling()

    tasks = [
        asyncio.create_task(
            run_until_cancelled(worker, container.settings.worker_interval_s, stop),
            name=f"zhiyin-worker-{getattr(worker, 'name', type(worker).__name__)}",
        )
        for worker in container.workers
    ]
    stop_task = asyncio.create_task(stop.wait(), name="zhiyin-background-stop")

    try:
        done, _ = await asyncio.wait(
            {stop_task, *tasks}, return_when=asyncio.FIRST_COMPLETED
        )
        failed = next((task for task in done if task is not stop_task), None)
        if failed is not None:
            await failed
    finally:
        stop.set()
        stop_task.cancel()
        for task in tasks:
            task.cancel()
        for task in [stop_task, *tasks]:
            # 某个 Worker 已失败时，它的异常已在上面通过
            # `await failed` 向外传递；清理阶段不要再抛一次而掩盖原始栈。
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

        stop_polling = getattr(scheduler, "stop_polling", None)
        if callable(stop_polling):
            await stop_polling()

        stop_event_polling = getattr(event_bus, "stop_polling", None)
        if callable(stop_event_polling):
            await stop_event_polling()

        for closable in reversed(container.extra.get("closables", [])):
            close = getattr(closable, "aclose", None) or getattr(closable, "close", None)
            if not callable(close):
                continue
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("关闭后台进程资源失败：%s", type(closable).__name__)

        for signum in installed_signals:
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(signum)


__all__ = [
    "Runnable",
    "run_background_container",
    "run_forever",
    "run_until_cancelled",
]
