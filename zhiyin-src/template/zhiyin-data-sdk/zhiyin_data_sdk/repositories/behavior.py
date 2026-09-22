"""行为日志写入与查询（behavior_log）。

行为日志是北极星指标的唯一事实来源，也是复盘主动干预的唯一触发信号来源
（不允许系统自嗨式打扰）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Sequence

from zhiyin_kernel.blackboard import BehaviorLog
from zhiyin_kernel.enums import BehaviorEventType


class BehaviorRepository(ABC):
    """行为日志 Repository。只追加，不修改。"""

    @abstractmethod
    async def append(self, log: BehaviorLog) -> BehaviorLog:
        """追加一条行为日志。"""

    @abstractmethod
    async def list_by_user(
        self,
        user_id: str,
        *,
        event_types: Optional[Sequence[BehaviorEventType]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[BehaviorLog]:
        """按时间倒序查询行为日志。"""

    @abstractmethod
    async def last_occurred_at(
        self, user_id: str, event_type: BehaviorEventType
    ) -> Optional[datetime]:
        """某类行为最后一次发生时间。

        复盘停滞检测的唯一依据：距今超过阈值才算"真实信号"。
        """
