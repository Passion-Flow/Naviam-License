"""Redis cache adapter 真实现测试（用 fakeredis 代替真 Redis）。

fakeredis 是 redis-py 兼容的内存实现，专为测试设计；行为与真 Redis 高度一致。
真生产用 RedisCache.from_settings(...) 走真 redis.asyncio.Redis。
"""
from __future__ import annotations

import pytest
from fakeredis import aioredis as fakeredis_async

from app.adapters.cache.redis.adapter import RedisCache


@pytest.fixture
async def cache():
    client = fakeredis_async.FakeRedis(decode_responses=False)
    yield RedisCache.from_client(client, db=0)
    await client.aclose()


@pytest.mark.asyncio
async def test_set_get_roundtrip(cache: RedisCache) -> None:
    await cache.set("k", b"hello", ttl_seconds=60)
    assert await cache.get("k") == b"hello"


@pytest.mark.asyncio
async def test_get_missing_returns_none(cache: RedisCache) -> None:
    assert await cache.get("does-not-exist") is None


@pytest.mark.asyncio
async def test_delete(cache: RedisCache) -> None:
    await cache.set("k", b"v")
    assert await cache.exists("k") is True
    await cache.delete("k")
    assert await cache.exists("k") is False


@pytest.mark.asyncio
async def test_incr(cache: RedisCache) -> None:
    assert await cache.incr("counter") == 1
    assert await cache.incr("counter") == 2
    assert await cache.incr("counter", amount=5) == 7


@pytest.mark.asyncio
async def test_sadd_smembers(cache: RedisCache) -> None:
    await cache.sadd("group", "alice", "bob", "alice")  # alice 去重
    members = await cache.smembers("group")
    assert members == {"alice", "bob"}


@pytest.mark.asyncio
async def test_hset_hgetall(cache: RedisCache) -> None:
    await cache.hset("user:1", {"name": "alice", "role": "admin"})
    got = await cache.hgetall("user:1")
    assert got == {"name": "alice", "role": "admin"}


@pytest.mark.asyncio
async def test_health_check(cache: RedisCache) -> None:
    assert await cache.health_check() is True


@pytest.mark.asyncio
async def test_binary_safe(cache: RedisCache) -> None:
    """bytes 进 bytes 出，不被解码篡改。"""
    payload = b"\x00\x01\xff\xfe binary"
    await cache.set("bin", payload)
    assert await cache.get("bin") == payload
