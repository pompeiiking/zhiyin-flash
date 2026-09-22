"""读缓存守卫。

缓存最容易出的两类问题是**静默**的：键每次都不一样（看着在用、其实每次都未命中），
以及失效漏了一处（用户改完画像、界面还是旧的）。这两类都不会抛异常、也不会让
接口变红，只能靠对着契约断言。

本文件守四条口径（与 `ports/cache.py` 的 docstring 一一对应）：

1. 命中即不调 loader（缓存真的省掉了一次聚合读）；
2. TTL 与失效事件来自**动态资源策略**，不是写死在代码里；
3. 失效是整片（`invalidate_for_event` 清掉该片所有键）；
4. 缓存故障一律退回直读，且**不缓存失败结果**。
"""

from __future__ import annotations

import pytest

from zhiyin_business.ports.cache import ReadCacheService, cache_key as port_cache_key
from zhiyin_business.services.read_cache import DefaultReadCacheService, cache_key
from zhiyin_infrastructure.local.cache import InMemoryCache
from zhiyin_kernel import dynamic_config
from zhiyin_kernel.registry import CacheNamespaceSpec, CachePolicy


POLICY = CachePolicy(
    default_ttl_s=120,
    namespaces=[
        CacheNamespaceSpec(
            namespace="workspace",
            ttl_s=20,
            invalidate_on=["profile_field_updated", "session_changed"],
        ),
        CacheNamespaceSpec(
            namespace="report",
            ttl_s=900,
            invalidate_on=["asset_version_changed"],
        ),
    ],
)


@pytest.fixture(autouse=True)
def _policy_snapshot():
    """装载策略快照，用完还原 —— 快照是进程级全局，不还原会串到下一条用例。"""
    before = dynamic_config.snapshot()
    dynamic_config.configure(
        dynamic_config.DynamicConfigSnapshot(cache=POLICY, source="test")
    )
    yield
    dynamic_config.configure(before)


def _service() -> DefaultReadCacheService:
    return DefaultReadCacheService(InMemoryCache())


async def test_hit_does_not_call_loader_again() -> None:
    """同一个键第二次读必须命中，loader 只跑一次。"""
    calls = 0

    async def loader() -> dict:
        nonlocal calls
        calls += 1
        return {"value": calls}

    cache = _service()
    key = cache_key("user-1")

    first = await cache.get_or_load("workspace", key, loader)
    second = await cache.get_or_load("workspace", key, loader)

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert calls == 1
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


async def test_different_keys_do_not_collide() -> None:
    """键里的片段必须真的进缓存键 —— 否则两个用户会互相看到对方的数据。"""
    cache = _service()

    async def loader_a() -> str:
        return "A"

    async def loader_b() -> str:
        return "B"

    assert await cache.get_or_load("workspace", cache_key("u1"), loader_a) == "A"
    assert await cache.get_or_load("workspace", cache_key("u2"), loader_b) == "B"
    assert cache.stats()["misses"] == 2


async def test_ttl_comes_from_policy_not_code() -> None:
    """每片的 TTL 取动态资源；策略里没有的片退回落日 TTL，而不是永久缓存。"""
    cache = _service()
    assert cache.namespace_ttl("workspace") == 20
    assert cache.namespace_ttl("report") == 900
    assert cache.namespace_ttl("未登记的片") == 120  # default_ttl_s


async def test_invalidate_for_event_clears_whole_namespace() -> None:
    """画像一变，工作台整片失效 —— 逐键判断迟早会漏，漏了就是"改完看不到"。"""
    calls = 0

    async def loader() -> str:
        nonlocal calls
        calls += 1
        return f"v{calls}"

    cache = _service()
    await cache.get_or_load("workspace", cache_key("u1"), loader)
    await cache.get_or_load("workspace", cache_key("u2"), loader)

    await cache.invalidate_for_event("profile_field_updated")

    assert await cache.get_or_load("workspace", cache_key("u1"), loader) == "v3"
    assert await cache.get_or_load("workspace", cache_key("u2"), loader) == "v4"
    assert calls == 4


async def test_unrelated_event_does_not_invalidate() -> None:
    """不在策略里的事件不该误伤缓存（否则命中率永远是 0，缓存等于没上）。"""
    calls = 0

    async def loader() -> str:
        nonlocal calls
        calls += 1
        return "v"

    cache = _service()
    await cache.get_or_load("workspace", cache_key("u1"), loader)
    await cache.invalidate_for_event("没有任何片声明的事件")
    await cache.get_or_load("workspace", cache_key("u1"), loader)

    assert calls == 1


async def test_loader_failure_is_not_cached() -> None:
    """loader 抛错时不得把"错误/空值"写进缓存 —— 那会把一次抖动放大成 TTL 长的故障。"""
    cache = _service()
    attempts = 0

    async def failing() -> str:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("依赖不可用")

    with pytest.raises(RuntimeError):
        await cache.get_or_load("workspace", cache_key("u1"), failing)
    with pytest.raises(RuntimeError):
        await cache.get_or_load("workspace", cache_key("u1"), failing)

    assert attempts == 2
    assert cache.stats()["misses"] == 2


async def test_broken_cache_falls_back_to_direct_read() -> None:
    """缓存整条链路不可用时，读侧仍要返回真实数据，只是每次都直读。"""
    class BrokenCache(InMemoryCache):
        async def get(self, namespace: str, key: str):
            raise ConnectionError("redis down")

        async def set(self, namespace: str, key: str, value: str, *, ttl_s=None):
            raise ConnectionError("redis down")

        async def clear_namespace(self, namespace: str) -> None:
            raise ConnectionError("redis down")

    calls = 0

    async def loader() -> dict:
        nonlocal calls
        calls += 1
        return {"value": calls}

    cache = DefaultReadCacheService(BrokenCache())
    first = await cache.get_or_load("workspace", cache_key("u1"), loader)
    second = await cache.get_or_load("workspace", cache_key("u1"), loader)
    await cache.invalidate_for_event("profile_field_updated")

    assert first == {"value": 1}
    assert second == {"value": 2}
    assert cache.stats()["errors"] >= 3


async def test_stats_lists_policy_namespaces() -> None:
    """`/healthz` 靠它回答"缓存到底有没有在工作"：策略里的片必须出现。"""
    stats = _service().stats()
    assert {item["namespace"] for item in stats["namespaces"]} == {"workspace", "report"}
    assert stats["default_ttl_s"] == 120
    assert stats["hit_rate"] is None  # 冷启动：还没有请求


def test_service_implements_the_port() -> None:
    """实现必须真的是 Port 的子类，否则装配处换实现时签名悄悄漂移。"""
    assert issubclass(DefaultReadCacheService, ReadCacheService)


def test_cache_key_is_colon_free_and_single_source() -> None:
    """键里不许出现冒号 —— 这条约束是"缓存静默失效"的根因，必须钉住。

    缓存网关把 `namespace:key` 拼成最终键，键里再带冒号会被它直接拒掉。
    拒掉的表现不是报错给用户，而是**每一次读写都抛异常**，被"故障直读"接住：
    缓存装上了、`/healthz` 也报得出策略，命中率却永远是 0。

    契约里的 `cache_key` 与实现里的 `cache_key` 必须是同一个函数，
    否则两边各拼一套、迟早又拼出带冒号的键。
    """
    assert cache_key is port_cache_key
    for built in (
        cache_key("u1"),
        cache_key("u1", "latest"),
        cache_key("u1", 3),
    ):
        assert ":" not in built, f"缓存键不能带冒号：{built!r}"


async def test_read_cache_is_wired_into_the_read_side() -> None:
    """装配守卫：读缓存必须真的接到**读侧**（Facade），不能只给编排器。

    只把缓存交给编排器（写侧失效）是个很隐蔽的装配错误：缓存对象存在、
    策略装上了、`/healthz` 的 `namespaces` 也报得出来，但**没有任何一次读经过它**
    —— hits/misses 恒为 0，"缓存装好了"看起来又是真的。
    实测就是这么漏的：`get_workspace` 走了直读分支，读缓存等于没上。
    """
    from pathlib import Path

    from zhiyin_boot import Settings, build_container

    data_dir = Path(__file__).resolve().parents[1] / "data"
    container = build_container(
        Settings(
            env="test",
            local_data_dir=str(data_dir),
            local_registry_dir=str(data_dir / "registry"),
            local_knowledge_dir=str(data_dir / "knowledge"),
            local_object_dir=str(data_dir / "objects"),
            use_remote_llm=True,
            llm_api_key="sk-test",
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
        )
    )
    assert container.read_cache is not None
    assert container.facade is not None

    await container.facade.get_workspace("cache-wiring-probe")
    after_first = container.read_cache.stats()
    await container.facade.get_workspace("cache-wiring-probe")
    after_second = container.read_cache.stats()

    assert after_first["misses"] >= 1, "第一次读没有经过缓存 —— Facade 没接上读缓存"
    assert after_second["hits"] >= 1, "第二次读没有命中 —— 键或失效口径不对"
