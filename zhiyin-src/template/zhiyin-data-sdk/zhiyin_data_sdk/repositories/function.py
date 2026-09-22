"""功能块的持久化契约：关键节点日历与跟踪时间线。

为什么必须有这两条
------------------
它们此前**只活在 `DefaultFunctionService` 的进程内存里**（两个 dict）。后果是：

- 重启一次，学生自己导进去的关键节点、以及教练的复盘时间线**全部消失**；
- 多实例部署时，A 实例写进去的节点 B 实例读不到 —— 这是"看起来能用"的服务最坏的形态。

这两类都是**用户可见的核心数据**（工作台 ④⑤ 层读它们），不是缓存，
所以按语义各建一张表，而不是塞进一张 JSONB 万能表 —— 万能表把字段约束全丢掉，
写错一个键要等到读的时候才知道。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from zhiyin_kernel.assets import CalendarNode, TrackEvent


class CalendarNodeRepository(ABC):
    """关键节点日历（规划师写入、教练读取、工作台展示）。"""

    @abstractmethod
    async def list_nodes(self, user_id: str) -> list[CalendarNode]:
        """列出用户的全部节点，按到期时间升序（没有 due_at 的排最后）。"""

    @abstractmethod
    async def upsert_node(self, user_id: str, node: CalendarNode) -> CalendarNode:
        """写入一个节点。同 `node_id` 覆盖 —— 规划师重排计划时不该留下两份。"""

    @abstractmethod
    async def delete_node(self, user_id: str, node_id: str) -> int:
        """删除节点，返回删除条数（0 表示本来就没有）。"""


class TrackEventRepository(ABC):
    """跟踪时间线（复盘与教练消息的载体）。"""

    @abstractmethod
    async def list_events(self, user_id: str, *, limit: int = 50) -> list[TrackEvent]:
        """按发生时间倒序取最近的事件。"""

    @abstractmethod
    async def append_event(self, user_id: str, event: TrackEvent) -> TrackEvent:
        """追加一条事件。时间线只追加、不改写。"""


class NotificationRepository(ABC):
    """教练通知的**读侧**。

    通知的写侧是 `NotifyGateway.push`（已经落 `orc_notification`）；
    这里补的是读侧 —— 此前 `FunctionService` 自己拿一个进程内队列当读侧，
    于是"库里明明写了通知，前端却什么都读不到"。
    """

    @abstractmethod
    async def list_pending(self, user_id: str) -> list[dict]:
        """取出该用户未读的通知（按创建时间倒序）。"""

    @abstractmethod
    async def mark_read(self, user_id: str, message_id: str) -> int:
        """标记已读，返回影响条数。"""

    # ---------- 打扰度控制的状态（从通知历史推导，不另存一份） ----------
    #
    # "上次什么时候提醒过他""这周已经提醒几次"曾经是 Worker 的进程内字典。
    # 多实例部署时每个进程各记一份，同一个用户会被提醒多次 —— 而"不打扰"恰恰是
    # 这套产品最重要的克制。这两条把它变成**从通知历史上算**：
    # 状态只有一份，就是已经发出去的那些通知本身（与"成就从行为日志推导"同一思路）。

    @abstractmethod
    async def last_sent_at(self, user_id: str) -> Optional[datetime]:
        """最近一次给这个用户发通知的时间；从没发过返回 None。冷却期判定用它。"""

    @abstractmethod
    async def count_since(self, user_id: str, since: datetime) -> int:
        """`since` 之后给这个用户发过几条。窗口内打扰上限用它。"""


__all__ = [
    "CalendarNodeRepository",
    "NotificationRepository",
    "TrackEventRepository",
]
