"""Redis 缓存实现。

缓存只放可重建的读侧数据，不作为唯一事实来源。
"""

from __future__ import annotations

from typing import Optional, Sequence

import redis.asyncio as redis

from zhiyin_data_sdk.gateways.cache import CacheGateway


class RedisCacheGateway(CacheGateway):
    """基于 Redis 的缓存 Gateway。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        url: str,
        *,
        key_prefix: str = "zhiyin",
        default_ttl_s: int = 300,
    ) -> None:
        self._client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        self._key_prefix = key_prefix.rstrip(":")
        self._default_ttl_s = default_ttl_s

    def _key(self, namespace: str, key: str) -> str:
        _validate_segment(namespace, "namespace")
        _validate_segment(key, "key")
        return f"{self._key_prefix}:{namespace}:{key}"

    def _namespace_set_key(self, namespace: str) -> str:
        _validate_segment(namespace, "namespace")
        return f"{self._key_prefix}:__ns__:{namespace}"

    async def get(self, namespace: str, key: str) -> Optional[str]:
        return await self._client.get(self._key(namespace, key))

    async def set(
        self, namespace: str, key: str, value: str, *, ttl_s: Optional[int] = None
    ) -> None:
        ttl = self._default_ttl_s if ttl_s is None else ttl_s
        value_key = self._key(namespace, key)
        set_key = self._namespace_set_key(namespace)
        async with self._client.pipeline(transaction=True) as pipe:
            if ttl and ttl > 0:
                pipe.set(value_key, value, ex=ttl)
                pipe.expire(set_key, ttl)
            else:
                pipe.set(value_key, value)
            pipe.sadd(set_key, key)
            await pipe.execute()

    async def delete(self, namespace: str, key: str) -> None:
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.delete(self._key(namespace, key))
            pipe.srem(self._namespace_set_key(namespace), key)
            await pipe.execute()

    async def delete_many(self, namespace: str, keys: Sequence[str]) -> int:
        if not keys:
            return 0
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.delete(*[self._key(namespace, key) for key in keys])
            pipe.srem(self._namespace_set_key(namespace), *keys)
            results = await pipe.execute()
        return int(results[0])

    async def clear_namespace(self, namespace: str) -> None:
        set_key = self._namespace_set_key(namespace)
        keys = list(await self._client.smembers(set_key))
        async with self._client.pipeline(transaction=True) as pipe:
            if keys:
                pipe.delete(*[self._key(namespace, key) for key in keys])
            pipe.delete(set_key)
            await pipe.execute()

    async def aclose(self) -> None:
        await self._client.aclose()


def _validate_segment(value: str, label: str) -> None:
    if not value or ":" in value or value == "__ns__":
        raise ValueError(f"Redis 缓存 {label} 不能为空且不能包含冒号：{value!r}")


__all__ = ["RedisCacheGateway"]
