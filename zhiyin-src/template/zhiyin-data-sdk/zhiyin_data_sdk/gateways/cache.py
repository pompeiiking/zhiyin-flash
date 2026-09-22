"""缓存 Gateway。

为什么要 namespace 作为必填参数
--------------------------------
缓存最容易制造耦合的地方是"键怎么拼"。若把拼键交给调用方，很快就会出现
`f"{user_id}:report"` 这种散落各处的字符串，改一处缓存策略要全仓搜。
因此本契约把 `namespace` 提升为必填参数（`profile` / `workspace` / `retrieval`），
键的拼装与失效范围因此可被统一控制。

口径：
- 缓存**只放可重建的读侧数据**，不得成为唯一事实来源；
- 写侧不缓存，避免"缓存与权威数据不一致"；
- `ttl_s=None` 表示用实现侧默认 TTL，`0` 表示不过期（谨慎使用）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence


class CacheGateway(ABC):
    """缓存 Port。"""

    @abstractmethod
    async def get(self, namespace: str, key: str) -> Optional[str]:
        """读取缓存。未命中返回 None（未命中不是错误）。"""

    @abstractmethod
    async def set(
        self, namespace: str, key: str, value: str, *, ttl_s: Optional[int] = None
    ) -> None:
        """写入缓存。"""

    @abstractmethod
    async def delete(self, namespace: str, key: str) -> None:
        """删除单个键。"""

    @abstractmethod
    async def delete_many(self, namespace: str, keys: Sequence[str]) -> int:
        """批量删除，返回删除条数。"""

    @abstractmethod
    async def clear_namespace(self, namespace: str) -> None:
        """清空命名空间。读模型结构变化时用它做整体失效。"""


__all__ = ["CacheGateway"]
