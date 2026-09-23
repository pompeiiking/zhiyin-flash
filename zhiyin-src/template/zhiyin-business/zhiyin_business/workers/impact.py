"""影响面传播 Worker。

职责：消费画像字段更新事件 → 调 `AssetService.propagate` → 只重算受影响片段。
本类**不实现重算范围判定**（那在 `policies/impact.py`），只负责"什么时候跑、跑谁"。

消费方式：向事件总线订阅 `profile_field_updated`，处理器把事件放进内部队列；
`run_once`（由驱动方按间隔轮询）批量取出、按 (user_id) 聚合字段键后调一次
`propagate`，避免同一用户连续改 5 个字段触发 5 次传播。

幂等要求（`Worker` 基类已声明）：同一字段可能被重复投递，`run_once` 以
`event_id` 去重，可重入。
"""

from __future__ import annotations

import asyncio

from zhiyin_business.ports.blackboard import AssetService
from zhiyin_business.ports.ai_tasks import AiTaskService
from zhiyin_kernel.enums import BehaviorEventType
from zhiyin_kernel.worker import Worker
from zhiyin_orchestration import DomainEvent, EventBus

_PROFILE_FIELD_UPDATED = BehaviorEventType.PROFILE_FIELD_UPDATED.value


class ImpactPropagationWorker(Worker):
    """影响面传播执行者。"""

    name = "impact"
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        assets: AssetService,
        event_bus: EventBus,
        *,
        ai_tasks: AiTaskService | None = None,
    ) -> None:
        self._assets = assets
        self._event_bus = event_bus
        # 画像变了，**派生内容也要作废**：资产走 propagate 重算，
        # AI 任务的产出（维度解读 / 报告小结 / 待办建议…）走 invalidate 作废。
        # 少了这一步，缓存里那份基于旧画像的解读会被当成最新的用 ——
        # 而缓存现在是跨重启的（`ai_task_result` 表），不作废就会一直错下去。
        self._ai_tasks = ai_tasks
        self._queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        # 去重表必须是**有序**的：淘汰要按"最早进来的先丢"，用 set 做不到
        # （`list(set)[-1000:]` 保住的是任意 1000 条，一次能忘掉 9000 个 id）。
        self._seen: dict[str, None] = {}
        self._seen_limit = 10_000
        event_bus.subscribe(_PROFILE_FIELD_UPDATED, self._on_event)

    async def _on_event(self, event: DomainEvent) -> None:
        await self._queue.put(event)

    async def run_once(self) -> int:
        """处理一轮待传播的画像字段更新，返回本轮收集的事件条数（0 = 无待处理）。

        顺序要求：**先出队、再处理、成功后才记去重**。
        此前是"出队即记 `_seen`"，于是 `propagate` 抛错时这一批剩余用户的工作不会执行，
        而它们的 event_id 已经进了去重表 —— 驱动方重试也会被过滤掉，**工作永久丢失**。
        """
        batch: dict[str, set[str]] = {}
        fresh: set[str] = set()
        events: list[DomainEvent] = []
        while True:
            try:
                event = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if event.event_id in self._seen:
                continue
            user_id = event.payload.get("user_id")
            field_key = event.payload.get("field_key")
            if not user_id or not field_key:
                # 载荷不全的事件重试多少次都没用：直接记去重，不留在队列里反复出现。
                self._mark_seen(event.event_id)
                continue
            batch.setdefault(str(user_id), set()).add(str(field_key))
            if event.payload.get("is_new"):
                # 新出现的一类字段：它不在任何资产的依赖清单里（清单是生成时的快照），
                # 所以不能只按"命中依赖"筛 —— 见 AssetService.propagate 的 mark_all。
                fresh.add(str(user_id))
            events.append(event)

        done = 0
        for user_id, keys in batch.items():
            try:
                await self._assets.propagate(
                    user_id, sorted(keys), mark_all=user_id in fresh
                )
            except Exception:  # noqa: BLE001 - 单用户失败不能拖垮整批
                # 不记去重：这批事件还没成功，绝不能让它们"看起来已处理"。
                # 直接抛给驱动方（`zhiyin_boot.workers` 会记日志并按间隔重试）。
                raise
            done += 1

        for event in events:
            self._mark_seen(event.event_id)
        return done

    def _mark_seen(self, event_id: str) -> None:
        """记入去重表，并按"最早先出"淘汰，保证表大小有界且不误忘最近的。"""
        self._seen[event_id] = None
        while len(self._seen) > self._seen_limit:
            self._seen.pop(next(iter(self._seen)))


__all__ = ["ImpactPropagationWorker"]
