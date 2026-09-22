"""主动事件 / 停滞检测 Worker。

产品硬约束：**不允许系统自嗨式打扰**。是否打扰只由行为日志的真实信号决定，
并受三个参数约束——停滞阈值 / 冷却期 / 打扰上限。

这三个参数**不在本文件**，也不在 `Settings`：读
`RegistryRepository.get_policy_params("intervention")`
（`data/registry/policy_params.json`，口径已确认）。
未配置或状态为 draft 时一律静默不打扰。

"算不算有动作"的口径（作答 / 认领差距 / 选择方案 / 勾任务 / 更新画像；纯浏览不算）
落在 `types(*_ACTION_EVENTS)`；判定本身在 `InterventionPolicy`，本类只负责
"到点扫描 + 按判定结果触发提醒"。

可扫描用户由 `user_provider` 提供（boot 装配时接用户存储的枚举能力）——
行为日志 Port 没有"列出全部用户"的读法，不为本 Worker 破例加。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, Sequence

from zhiyin_business.policies.intervention import InterventionPolicy
from zhiyin_business.ports.blackboard import BehaviorService
from zhiyin_data_sdk.repositories import RegistryRepository
from zhiyin_data_sdk.repositories import NotificationRepository
from zhiyin_kernel.enums import BehaviorEventType
from zhiyin_kernel.worker import Worker
from zhiyin_orchestration import Notifier, NotifyMessage, Scheduler

logger = logging.getLogger(__name__)

_ACTION_EVENTS: tuple[BehaviorEventType, ...] = (
    BehaviorEventType.ANSWER,
    BehaviorEventType.GAP_CLAIM,
    BehaviorEventType.DECISION_SELECT,
    BehaviorEventType.DECISION_RESELECT,
    BehaviorEventType.TASK_DONE,
    BehaviorEventType.PROFILE_FIELD_UPDATED,
    BehaviorEventType.REVIEW,
)

UserProvider = Callable[[], Sequence[str] | Awaitable[Sequence[str]]]
PolicyFactory = Callable[[Mapping[str, Any]], InterventionPolicy]


class ActiveEventWorker(Worker):
    """停滞检测与主动干预执行者。"""

    name = "active_event"
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        behaviors: BehaviorService,
        policy_factory: PolicyFactory,
        registry: RegistryRepository,
        notifications: NotificationRepository,
        scheduler: Scheduler,
        notifier: Notifier,
        user_provider: UserProvider | None = None,
    ) -> None:
        """`policy_factory` 每轮用动态资源里最新的参数构造规则实例——
        调阈值不需要发版，也不需要重启 Worker。"""
        self._behaviors = behaviors
        self._policy_factory = policy_factory
        self._registry = registry
        # 打扰度控制的状态从这个仓储**读**（不是自己记）：它同时是通知读侧，
        # `list_pending` 与节流判定读的是同一份历史。
        self._notifications = notifications
        self._scheduler = scheduler
        self._notifier = notifier
        self._user_provider = user_provider
        # 冷却与窗口内打扰计数**不再自己记**：从通知历史上算。
        # 进程内字典在多实例下会各记一份，同一个用户被提醒多次 ——
        # 而"不打扰"是这套产品最重要的克制（见 NotificationRepository 的说明）。

    async def run_once(self) -> int:
        """扫描一轮停滞信号，返回本轮触发的干预条数（0 = 不打扰）。"""
        params = await self._registry.get_policy_params("intervention")
        if params is None or params.status != "confirmed":
            return 0
        value = params.value
        window_days = int(value.get("window_days", 7))
        policy = self._policy_factory(value)
        now = datetime.now(timezone.utc)

        user_ids: Sequence[str] = ()
        if self._user_provider is not None:
            provided = self._user_provider()
            if isinstance(provided, Awaitable):
                provided = await provided
            user_ids = provided

        triggered = 0
        for user_id in user_ids:
            days_inactive = await self._days_inactive(user_id)
            if days_inactive is None:
                continue
            window_start = now - timedelta(days=window_days)
            if not policy.should_intervene(
                days_inactive=days_inactive,
                last_notified_at=await self._notifications.last_sent_at(user_id),
                notifications_in_window=await self._notifications.count_since(
                    user_id, window_start
                ),
                now=now,
            ):
                continue
            title, body = await self._intervention_copy(days_inactive)
            if not title:
                # 文案没配就不打扰 —— 主动干预是"宁可不发"的一侧。
                continue
            await self._notifier.push(
                NotifyMessage(user_id=user_id, title=title, body=body, channel="in_app")
            )
            triggered += 1
        return triggered

    async def _intervention_copy(self, days_inactive: int) -> tuple[str, str]:
        """主动干预的文案：来自动态资源，不在 Worker 里写中文。

        那句"距离你上一次关键动作已经 N 天"是**用户可见的产品文案**，
        与界面上的其它文案同一性质 —— 改它不该发一次版。
        `{days}` 是占位符；模板里没有它时原样给出，配错模板最多文案不完整，
        不会抛异常把整轮扫描打断。
        """
        bundle = await self._registry.get_copy_bundle()
        title = bundle.get("notify.stall.title", "")
        template = bundle.get("notify.stall.body", "")
        if not title or not template:
            logger.warning("主动干预文案未配置（notify.stall.title / body），本轮跳过提醒")
            return "", ""
        body = template.replace("{days}", str(days_inactive)) if "{days}" in template else template
        return title, body

    async def _days_inactive(self, user_id: str) -> int | None:
        """距最近一次"关键动作"的天数；从无任何动作 → None（新用户不打扰）。"""
        days: list[int] = []
        for event_type in _ACTION_EVENTS:
            value = await self._behaviors.days_since_last(user_id, event_type)
            if value is not None:
                days.append(value)
        return min(days) if days else None


__all__ = ["ActiveEventWorker"]
