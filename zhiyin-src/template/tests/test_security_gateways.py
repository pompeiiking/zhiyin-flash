"""真安全实现与真限流的守卫。

这两条以前是 no-op（不加密、不脱敏、恒放行），而装配报告照样显示"已装配" ——
比"缺"更坏的一种状态：看起来有这层保护，实际上一件事都没做。
这里守的是"真的做了"：

  · 加密：解出来是原文；**改一个字节就解不开**（认证加密）；
  · 脱敏：留头留尾、长度对得上，且不同 kind 规则不同；
  · 限流：放行 N 次之后拒掉，且**跨实例共享**（走 Redis，不是进程内计数）。
"""

from __future__ import annotations

import pytest

from zhiyin_infrastructure.security.crypto import CryptoSecurity

KEY = "k" * 40


def test_encrypt_round_trip_and_tamper_detection() -> None:
    sec = CryptoSecurity(KEY)
    plain = "这是一段需要保护的内容".encode()
    sealed = sec.encrypt(plain)
    assert sealed != plain, "密文与明文一样 —— 那等于没加密"
    assert sec.decrypt(sealed) == plain

    # 认证加密：改一个字节就解不开，而不是"解出来是乱码"
    broken = sealed[:-1] + bytes([sealed[-1] ^ 0x01])
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        sec.decrypt(broken)


def test_decrypt_refuses_plaintext_instead_of_passing_it_through() -> None:
    """不是本实现加的密 → 抛错，不静默返回原文（那会把明文当密文用）。"""
    with pytest.raises(ValueError):
        CryptoSecurity(KEY).decrypt(b"plain text")


def test_short_key_is_refused() -> None:
    with pytest.raises(ValueError):
        CryptoSecurity("too-short")


def test_masking_keeps_edges_and_hides_the_middle() -> None:
    sec = CryptoSecurity(KEY)
    phone = sec.mask("13800008000", kind="phone")
    assert phone.startswith("138") and phone.endswith("8000") and "*" in phone
    assert sec.mask("zhangsan@example.com", kind="email").endswith("@example.com")
    assert sec.mask("secret-token", kind="token") == "********"
    assert sec.mask("") == ""


async def test_redis_rate_limit_denies_after_the_quota() -> None:
    """令牌桶：前 3 次放行，第 4 次拒掉。

    这条需要真 Redis —— 限流必须共享状态，进程内计数在多实例下等于把额度乘以实例数。
    没有 Redis 时跳过，而不是假装通过。
    """
    pytest.importorskip("redis.asyncio")
    from zhiyin_infrastructure.redis.rate_limit import RedisRateLimit

    # 56379 = compose 里 Redis 发布到回环的端口（见 docker-compose.yml）
    limiter = RedisRateLimit("redis://127.0.0.1:56379/9", key_prefix="test-rl")
    try:
        await limiter._client.ping()  # noqa: SLF001 - 探活，不通就跳过
    except Exception:  # noqa: BLE001
        pytest.skip("本机没有可用的 Redis")

    key = "unit-test-quota"
    await limiter._client.delete(f"test-rl:rl:{key}")  # noqa: SLF001
    allowed = [await limiter.allow_async(key, limit=3, window_s=60) for _ in range(4)]
    assert allowed[:3] == [True, True, True]
    assert allowed[3] is False
