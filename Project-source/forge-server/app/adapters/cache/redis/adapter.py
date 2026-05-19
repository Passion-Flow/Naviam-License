"""Redis 适配器（redis.asyncio driver）。

设计：
- 用 `redis.asyncio.Redis` 单例 client（连接池由 redis-py 自管）
- 所有 method 严格按 Cache Protocol 契约
- 字符串以 bytes 返回（utf-8 由调用方处理；保持二进制安全）

测试期可通过 `from_client(...)` 注入 fakeredis 实例。
"""
from __future__ import annotations

from typing import Any

import redis.asyncio as redis_async

from app.adapters.cache.interface.protocol import Cache
from app.settings import Settings


class RedisCache(Cache):
    provider_name = "redis"

    def __init__(self, host: str, port: int, username: str, password: str, db: int) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._db = db
        self._client: redis_async.Redis | None = None

    @classmethod
    def from_settings(cls, settings: Settings, *, db: int) -> "RedisCache":
        return cls(
            host=settings.cache_host,
            port=settings.cache_port,
            username=settings.cache_username,
            password=settings.cache_password,
            db=db,
        )

    @classmethod
    def from_client(cls, client: redis_async.Redis, *, db: int = 0) -> "RedisCache":
        """测试钩子：注入已建好的 client（如 fakeredis.aioredis.FakeRedis）。"""
        instance = cls.__new__(cls)
        instance._host = ""
        instance._port = 0
        instance._username = ""
        instance._password = ""
        instance._db = db
        instance._client = client
        return instance

    async def connect(self) -> None:
        if self._client is not None:
            return
        kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "db": self._db,
            "decode_responses": False,  # 保持 bytes
        }
        if self._username:
            kwargs["username"] = self._username
        if self._password:
            kwargs["password"] = self._password
        self._client = redis_async.Redis(**kwargs)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        if self._client is None:
            await self.connect()
        try:
            return await self._client.ping()  # type: ignore[union-attr]
        except Exception:
            return False

    def _ensure(self) -> redis_async.Redis:
        if self._client is None:
            raise RuntimeError("Redis client not connected; call connect() first")
        return self._client

    # ── 基础读写 ────────────────────────────────────────────
    async def get(self, key: str) -> bytes | None:
        return await self._ensure().get(key)

    async def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        await self._ensure().set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._ensure().delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._ensure().exists(key))

    # ── 原子计数 ────────────────────────────────────────────
    async def incr(self, key: str, *, amount: int = 1, ttl_seconds: int | None = None) -> int:
        client = self._ensure()
        value = await client.incrby(key, amount)
        if ttl_seconds is not None:
            await client.expire(key, ttl_seconds)
        return int(value)

    # ── 集合 ────────────────────────────────────────────────
    async def sadd(self, key: str, *members: str, ttl_seconds: int | None = None) -> int:
        client = self._ensure()
        added = await client.sadd(key, *members)
        if ttl_seconds is not None:
            await client.expire(key, ttl_seconds)
        return int(added)

    async def smembers(self, key: str) -> set[str]:
        raw = await self._ensure().smembers(key)
        return {m.decode("utf-8") if isinstance(m, bytes) else m for m in raw}

    async def srem(self, key: str, *members: str) -> int:
        if not members:
            return 0
        return int(await self._ensure().srem(key, *members))

    # ── 哈希 ────────────────────────────────────────────────
    async def hset(self, key: str, mapping: dict[str, Any], *, ttl_seconds: int | None = None) -> None:
        if not mapping:
            return
        client = self._ensure()
        # redis-py 接受字符串 + bytes/str 值
        normalized = {k: (v if isinstance(v, (str, bytes)) else str(v)) for k, v in mapping.items()}
        await client.hset(key, mapping=normalized)
        if ttl_seconds is not None:
            await client.expire(key, ttl_seconds)

    async def hgetall(self, key: str) -> dict[str, Any]:
        raw = await self._ensure().hgetall(key)
        return {
            (k.decode("utf-8") if isinstance(k, bytes) else k):
                (v.decode("utf-8") if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }
