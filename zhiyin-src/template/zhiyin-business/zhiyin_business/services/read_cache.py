"""读缓存实现：JSON 序列化 + 按策略失效 + 故障直读。

为什么不做成装饰器 / 中间件
--------------------------
这一层的取值点是"**哪一次读值得缓存**"，那是业务判断（工作台聚合值得、
单条笔记不值得），不是横切关注点。写成中间件会把所有读都卷进来，
然后靠"排除名单"往回退 —— 最后没人说得清哪次读被缓存过。

命中率看得见
------------
`stats()` 报每一片的命中/未命中。缓存最坏的样子不是"没用上"，
而是"以为在用、其实键每次都不同"（例如键里带了时间戳）——
命中率是唯一能戳穿它的东西。
"""

from __future__ import annotations

import json
import inspect
import logging
from typing import Any, Awaitable, Callable, Optional, TypeVar

from pydantic import BaseModel

from zhiyin_business.ports.cache import ReadCacheService, cache_key
from zhiyin_data_sdk.gateways.cache import CacheGateway
from zhiyin_kernel import dynamic_config
from zhiyin_kernel.registry import CachePolicy

logger = logging.getLogger(__name__)
T = TypeVar("T")

#: 策略读不到时的兜底：短 TTL。缓存参数缺失不该让读侧变成永久缓存。
FALLBACK_TTL_S = 30


class DefaultReadCacheService(ReadCacheService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, cache: CacheGateway) -> None:
        self._cache = cache
        self._hits = 0
        self._misses = 0
        self._errors = 0

    # ---------- 策略：每一片 TTL 多长、什么事件让它失效 ----------

    def _policy(self) -> CachePolicy | None:
        """策略来自进程内快照（动态资源装载的那一份），不额外读库。"""
        return dynamic_config.snapshot().cache

    def namespace_ttl(self, namespace: str) -> int:
        policy = self._policy()
        if policy is None:
            return FALLBACK_TTL_S
        for spec in policy.namespaces:
            if spec.namespace == namespace:
                return spec.ttl_s
        return policy.default_ttl_s

    def _namespaces_for_event(self, event: str) -> list[str]:
        policy = self._policy()
        if policy is None:
            return []
        return [spec.namespace for spec in policy.namespaces if event in spec.invalidate_on]

    # ---------- 读 ----------

    async def get_or_load(
        self,
        namespace: str,
        key: str,
        loader: Callable[[], Awaitable[T]],
        *,
        model: type[T] | None = None,
    ) -> T:
        cached: str | None = None
        try:
            cached = await self._cache.get(namespace, key)
        except Exception:  # noqa: BLE001 - 缓存读失败：直读，不阻塞
            self._errors += 1
            logger.warning("读缓存不可用（%s/%s），本次直读", namespace, key, exc_info=False)

        if cached is not None:
            try:
                self._hits += 1
                return _decode(cached, model)
            except Exception:  # noqa: BLE001 - 反序列化失败：当未命中
                logger.warning("缓存内容解不开（%s/%s），按未命中处理", namespace, key)

        self._misses += 1
        # 契约要求 loader 可等待。给了同步 loader 也照做，但**留痕**：
        # `await` 一个非可等待对象会直接 500，而这条路径只在缓存装配后才走到
        # （没装缓存时调用方走的是直读分支）—— 属于"上缓存才炸"的那一类。
        pending: Any = loader()
        if inspect.isawaitable(pending):
            value: Any = await pending
        else:
            logger.warning(
                "缓存 loader 不是可等待对象（%s/%s）—— 已按同步返回值处理",
                namespace,
                key,
            )
            value = pending
        try:
            await self._cache.set(
                namespace, key, _encode(value), ttl_s=self.namespace_ttl(namespace)
            )
        except Exception:  # noqa: BLE001 - 回填失败不影响这次读的结果
            self._errors += 1
            logger.warning("缓存回填失败（%s/%s）", namespace, key, exc_info=False)
        return value

    # ---------- 失效 ----------

    async def invalidate(self, namespace: str, key: Optional[str] = None) -> None:
        try:
            if key is None:
                await self._cache.clear_namespace(namespace)
            else:
                await self._cache.delete(namespace, key)
        except Exception:  # noqa: BLE001 - 失效失败：TTL 会让它自然过期
            self._errors += 1
            logger.warning("缓存失效失败（%s/%s）—— 该片会在 TTL 后自然过期", namespace, key)

    async def invalidate_for_event(self, event: str) -> None:
        namespaces = self._namespaces_for_event(event)
        if not namespaces:
            return
        for namespace in namespaces:
            # 整片失效：读模型之间有关联（画像一变，工作台 / 报告 / 采集清单都变），
            # 逐键判断迟早会漏，而"漏"的症状是用户改完看不到变化。
            await self.invalidate(namespace)

    # ---------- 自述 ----------

    def stats(self) -> dict[str, Any]:
        policy = self._policy()
        total = self._hits + self._misses
        return {
            "namespaces": [
                {
                    "namespace": spec.namespace,
                    "ttl_s": spec.ttl_s,
                    "invalidated_by": list(spec.invalidate_on),
                }
                for spec in (policy.namespaces if policy else [])
            ],
            "default_ttl_s": policy.default_ttl_s if policy else FALLBACK_TTL_S,
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "hit_rate": round(self._hits / total, 3) if total else None,
        }


def _encode(value: Any) -> str:
    """能把值变成字符串就行：pydantic 模型走它自己的序列化，其余走 json。"""
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(value, ensure_ascii=False, default=str)


def _decode(raw: str, model: Any = None) -> Any:
    """按模型反序列化（给了模型类时），否则按普通 JSON。"""
    if isinstance(model, type) and issubclass(model, BaseModel):
        return model.model_validate_json(raw)
    return json.loads(raw)


__all__ = ["DefaultReadCacheService", "cache_key"]
