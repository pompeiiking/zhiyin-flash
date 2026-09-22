"""本地内存缓存（InMemoryCache）。

第一期定位：让"读侧可缓存"这条口径有真实实现可跑（工作台聚合、检索结果），
并使缓存命名空间与失效范围在接口层就被固定下来。进程重启即失效 —— 这与
第一期"纯内存、可演示"的整体口径一致。

实现同一份 `CacheGateway` 契约，装配处改一行。
"""

from __future__ import annotations

import time
from typing import Optional, Sequence

from zhiyin_data_sdk.gateways.cache import CacheGateway


class InMemoryCache(CacheGateway):
    """按命名空间隔离、支持 TTL 的进程内缓存。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self, default_ttl_s: Optional[int] = 300) -> None:
        self._default_ttl_s = default_ttl_s
        # (namespace, key) → (value, expires_at | None)
        self._items: dict[tuple[str, str], tuple[str, Optional[float]]] = {}

    async def get(self, namespace: str, key: str) -> Optional[str]:
        entry = self._items.get((namespace, key))
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and expires_at <= time.monotonic():
            self._items.pop((namespace, key), None)
            return None
        return value

    async def set(
        self, namespace: str, key: str, value: str, *, ttl_s: Optional[int] = None
    ) -> None:
        effective = self._default_ttl_s if ttl_s is None else ttl_s
        expires_at = None if effective == 0 else time.monotonic() + effective
        self._items[(namespace, key)] = (value, expires_at)

    async def delete(self, namespace: str, key: str) -> None:
        self._items.pop((namespace, key), None)

    async def delete_many(self, namespace: str, keys: Sequence[str]) -> int:
        removed = 0
        for key in keys:
            if self._items.pop((namespace, key), None) is not None:
                removed += 1
        return removed

    async def clear_namespace(self, namespace: str) -> None:
        for item in [k for k in self._items if k[0] == namespace]:
            self._items.pop(item, None)


__all__ = ["InMemoryCache"]
