"""HeartbeatCollector —— 心跳记录的存储抽象。

业务代码通过 HeartbeatCollector 协议存取，**不**直接接 Redis 或 DB。
- InMemoryHeartbeatCollector：单元测试用 / 单实例小流量降级方案
- RedisHeartbeatCollector：（后续）借 adapters.cache.RedisCache 实现真正多实例可用

数据模型：
- record_heartbeat(record)：写入一条心跳；维护"license_id 最近 N 秒见过的指纹集合"
- recent_fingerprints(license_id, window)：返回近期上报过的指纹集合
- nonce_seen(license_id, nonce)：查 nonce 是否在 NONCE_TTL_SECONDS 内见过
- mark_nonce_seen(license_id, nonce)：标记 nonce 见过（写入短 TTL）
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.core.license.heartbeat.schema import NONCE_TTL_SECONDS


@dataclass(frozen=True, slots=True)
class HeartbeatRecord:
    license_id: str
    fingerprint: str
    received_at: datetime
    reported_at: datetime
    nonce: str
    api_key_id: str | None
    verifier_version: str


class HeartbeatCollector(Protocol):
    """心跳数据存取统一接口。"""

    async def record(self, record: HeartbeatRecord) -> None: ...

    async def recent_fingerprints(
        self,
        license_id: str,
        *,
        window: timedelta,
        now: datetime | None = None,
    ) -> set[str]: ...

    async def is_nonce_seen(self, license_id: str, nonce: str) -> bool: ...

    async def mark_nonce_seen(self, license_id: str, nonce: str) -> None: ...


class InMemoryHeartbeatCollector(HeartbeatCollector):
    """单元测试 + 单实例降级用。线程不安全（FastAPI 单实例单进程 OK）。

    生产请用 RedisHeartbeatCollector（多实例共享数据 + 自动过期）。
    """

    def __init__(self) -> None:
        # license_id → list[HeartbeatRecord]
        self._records: dict[str, list[HeartbeatRecord]] = defaultdict(list)
        # (license_id, nonce) → seen_at_monotonic
        self._nonces: dict[tuple[str, str], float] = {}

    async def record(self, record: HeartbeatRecord) -> None:
        self._records[record.license_id].append(record)

    async def recent_fingerprints(
        self,
        license_id: str,
        *,
        window: timedelta,
        now: datetime | None = None,
    ) -> set[str]:
        now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = now_utc - window
        return {
            r.fingerprint
            for r in self._records.get(license_id, [])
            if r.received_at >= cutoff
        }

    async def is_nonce_seen(self, license_id: str, nonce: str) -> bool:
        key = (license_id, nonce)
        seen_at = self._nonces.get(key)
        if seen_at is None:
            return False
        # 过期则清理
        if time.monotonic() - seen_at > NONCE_TTL_SECONDS:
            self._nonces.pop(key, None)
            return False
        return True

    async def mark_nonce_seen(self, license_id: str, nonce: str) -> None:
        self._nonces[(license_id, nonce)] = time.monotonic()
        # 顺手清理过期（避免内存无限增长）
        now = time.monotonic()
        expired = [k for k, t in self._nonces.items() if now - t > NONCE_TTL_SECONDS]
        for k in expired:
            self._nonces.pop(k, None)
