"""读缓存契约（业务侧）。

它描述的是**业务怎么用缓存**，不是缓存怎么实现 —— 实现是 `CacheGateway`
（`zhiyin_data_sdk` 的 Port，Redis / 进程内两种）。

三条口径写进契约本身，免得每个调用点各理解一遍：

1. **只放可重建的读模型**。缓存命中就省一次聚合读；丢了从权威存储重建。
   任何"只有缓存里有"的数据都不该走这条路 —— 那是把缓存当数据库。
2. **写侧不缓存，写完整片失效**。宁可失效得多一点（多读一次），
   也不要让用户看到自己刚改过、界面上还是旧的数据。
3. **缓存故障不阻塞**。Redis 挂了、序列化失败、键写坏了 —— 一律退回直读。
   缓存是加速器，不是依赖项。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")

#: 键内片段的分隔符。**不能用冒号**：缓存网关把 `namespace:key` 拼成最终键，
#: 键里再出现冒号会被它直接拒掉（`redis/cache.py::_validate_segment`）。
#: 用冒号拼键的代码不会报"我写错了"，只会每一次读写都抛错 —— 而读缓存的设计
#: 是"故障直读"，于是它静默退化成"每次都直读"：装上了、看着正常、一次没命中。
KEY_SEPARATOR = "|"


def cache_key(*parts: Any) -> str:
    """统一个键的拼法：把这次读的维度按顺序拼起来（`u1|latest`）。

    把拼键收在契约里，是为了让"哪一片、按什么维度缓存"一眼可读 ——
    散落的 f-string 迟早会出现 `u1` 与 `u1|` 这种看起来一样、实际命中不了的键。

    注意：**不要把 namespace 再拼进来**。namespace 是 `get_or_load` 的独立参数，
    网关会自己拼成 `zhiyin:<namespace>:<key>`；重复一次只会多一段没人维护的前缀。
    """
    return KEY_SEPARATOR.join(str(part) for part in parts)


class ReadCacheService(ABC):
    """读缓存：命中返回缓存、未命中调 loader 并回填；失败一律直读。"""

    @abstractmethod
    async def get_or_load(
        self,
        namespace: str,
        key: str,
        loader: Callable[[], Awaitable[T]],
        *,
        model: type[T] | None = None,
    ) -> T:
        """按策略缓存一次读。

        `namespace` 决定 TTL 与失效事件（策略在动态资源里）；
        `key` 由调用方给，必须是"能唯一确定这次读结果"的东西
        （例如 `workspace:{user_id}`、`report:{user_id}:{version}`）。
        `model` 给 pydantic 模型类时，缓存命中会**按模型反序列化**再返回 ——
        这样调用方拿到的永远是同一个类型，而不是"有时是模型、有时是 dict"。
        """

    @abstractmethod
    async def invalidate(self, namespace: str, key: Optional[str] = None) -> None:
        """失效一片或一个键。`key=None` 表示整片失效。"""

    @abstractmethod
    async def invalidate_for_event(self, event: str) -> None:
        """按**事件码**失效：策略里声明了哪些事件该让哪些片失效。

        这是写侧唯一需要知道的东西 —— 它说"发生了什么"，不需要知道
        "这会影响哪几片缓存"。映射关系在动态资源里，改它不发版。

        失效粒度是**整片**（不是单个键）：读模型之间是有关联的
        （画像一变，工作台、报告、采集清单都跟着变），逐键判断迟早会漏 ——
        漏掉的症状是"用户改完，界面上还是旧的"，那比多读一次贵得多。
        """

    @abstractmethod
    def namespace_ttl(self, namespace: str) -> int:
        """这一片的 TTL（秒）。策略里没有就退回落日 TTL。"""

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        """缓存自述：策略里的片、各自 TTL、命中/未命中计数。

        没有它，"缓存到底有没有在工作"就只能靠猜；`/healthz` 与运维排查要看得见。
        刻意做成同步：它只读进程内计数与已装载的策略快照，不碰任何连接，
        因此探针可以随时调它而不引入一次网络往返。
        """
