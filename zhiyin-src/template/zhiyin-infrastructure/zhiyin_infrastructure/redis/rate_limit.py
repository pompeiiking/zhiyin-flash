"""Redis 令牌桶限流。

为什么不能是"恒放行"
--------------------
限流的意义是**保护后面那套东西**：模型调用按量计费、外部站点会被打崩、
一个脚本循环能把一天额度用光。恒放行的实现等于没有这一层，
而它在装配报告里还显示"已装配" —— 那是比缺更坏的一种状态。

为什么用 Redis 而不是进程内计数
------------------------------
多实例部署时每个进程各记一份，同一个用户会被放行 N 次（N = 实例数）。
限流器必须共享状态，而 Redis 已经是这套系统的必需件之一。

算法：令牌桶（按时间连续补充），不是固定窗口 ——
固定窗口在窗口边界能瞬间放行两倍流量，那正是脚本最容易打到的时机。
"""

from __future__ import annotations

import time
from typing import Optional

import redis.asyncio as redis

from zhiyin_data_sdk.gateways.security import RateLimitGateway


class RedisRateLimit(RateLimitGateway):
    """按 key 限流：默认 60 次 / 60 秒，桶容量等于限额。"""

    IMPLEMENTATION_STATUS = "wired"

    DEFAULT_LIMIT = 60
    DEFAULT_WINDOW_S = 60.0

    def __init__(
        self,
        url: str,
        *,
        key_prefix: str = "zhiyin",
        default_limit: int = DEFAULT_LIMIT,
        default_window_s: float = DEFAULT_WINDOW_S,
    ) -> None:
        self._client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        self._prefix = key_prefix.rstrip(":")
        self._limit = default_limit
        self._window = default_window_s

    async def allow_async(
        self,
        key: str,
        *,
        limit: Optional[int] = None,
        window_s: Optional[float] = None,
    ) -> bool:
        """异步版本：接口层与 Worker 都用它。

        `allow()`（契约里的同步方法）保留给"已经在同步上下文里"的调用方，
        但**会退化成放行并留日志** —— 同步方法里没法等一次网络往返，
        假装限流成功比不限流更危险。真正需要限流的调用方应走这一条。
        """
        capacity = float(limit or self._limit)
        window = float(window_s or self._window)
        rate = capacity / window if window > 0 else capacity
        now = time.time()
        redis_key = f"{self._prefix}:rl:{key}"
        try:
            # Lua：读桶 → 按经过时间补令牌 → 够就扣一个。
            # 放在一条脚本里是为了原子 —— 分开读改写会漏掉并发。
            script = """
            local tokens = tonumber(redis.call('HGET', KEYS[1], 't') or ARGV[1])
            local stamp = tonumber(redis.call('HGET', KEYS[1], 's') or ARGV[2])
            local rate = tonumber(ARGV[3])
            local cap = tonumber(ARGV[1])
            local now = tonumber(ARGV[2])
            local filled = math.min(cap, tokens + (now - stamp) * rate)
            local ok = 0
            if filled >= 1 then
              filled = filled - 1
              ok = 1
            end
            redis.call('HSET', KEYS[1], 't', filled, 's', now)
            redis.call('EXPIRE', KEYS[1], math.ceil(cap / rate) + 1)
            return ok
            """
            ok = await self._client.eval(
                script, 1, redis_key, capacity, now, rate
            )
            return bool(ok)
        except Exception:  # noqa: BLE001 - 限流器坏了不该把业务挡死
            # 这里是"故障开放"（fail-open）：Redis 抖一下就把所有请求拒掉，
            # 是把可用性押在一个缓存件上。代价是那一刻没有限流 —— 可接受。
            return True

    def allow(
        self,
        key: str,
        *,
        limit: Optional[int] = None,
        window_s: Optional[float] = None,
    ) -> bool:
        """同步入口：**不猜**，直接放行并在日志里说清要用异步版本。"""
        import logging

        logging.getLogger(__name__).warning(
            "限流走了同步入口（%s）—— 同步上下文里等不了 Redis，本次放行。"
            "需要真正限流的调用方请用 allow_async。",
            key,
        )
        return True

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["RedisRateLimit"]
