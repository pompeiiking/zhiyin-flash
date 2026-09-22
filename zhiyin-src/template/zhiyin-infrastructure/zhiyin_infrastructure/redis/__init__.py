"""Redis 基础设施实现。

本包只承载缓存能力，不承载业务语义。
"""

from zhiyin_infrastructure.redis.cache import RedisCacheGateway

__all__ = ["RedisCacheGateway"]
