"""ApiKeyQuotaLimiter —— 按 (key_id, 当前 UTC 小时) 计数 → 超阈值返回 False。

存储：Cache（Redis）使用 `apikey:quota:{key_id}:{YYYYMMDDHH}` key，
ttl 1h；用 atomic INCR + EXPIRE 自动滑窗。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class _CacheLike(Protocol):
    async def incr(self, key: str, *, ttl_seconds: int) -> int: ...


class ApiKeyQuotaLimiter:
    def __init__(self, cache: _CacheLike | None, *, per_hour: int) -> None:
        self._cache = cache
        self._per_hour = per_hour

    @property
    def enabled(self) -> bool:
        return self._cache is not None and self._per_hour > 0

    async def check_and_inc(self, *, key_id: str) -> tuple[bool, int]:
        """Atomic 计数 +1，返回 (allowed, current_count)。"""
        if not self.enabled:
            return True, 0
        hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        key = f"apikey:quota:{key_id}:{hour}"
        count = await self._cache.incr(key, ttl_seconds=3600)  # type: ignore[union-attr]
        return count <= self._per_hour, count
