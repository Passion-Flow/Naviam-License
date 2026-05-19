"""LoginRateLimiter —— 防御 /auth/login 暴力破解。

策略：
- 计数键 = f"login:fail:{ip}:{username}"，避免被同 IP 跨多用户喷或单用户跨多 IP 喷绕过
- 每次失败 → `incr(key, ttl_seconds=window)`；若返回值 >= threshold → 拒绝
- 成功登录 → 显式 `delete(key)` 清掉对应 (ip, username) 计数
- 缺 cache 时退化为 no-op（开发期 / 极简部署）

Redis 的 `INCR` + `EXPIRE` 组合就是经典 fixed-window 计数器。这里没用 sliding log，
是因为 fixed-window 足够防住暴力破解，实现极简且原子。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _CacheLike(Protocol):
    async def incr(self, key: str, *, amount: int = 1, ttl_seconds: int | None = None) -> int: ...
    async def delete(self, key: str) -> None: ...
    async def get(self, key: str) -> bytes | None: ...


@dataclass(frozen=True, slots=True)
class RateLimitVerdict:
    """登录限流判定。

    allowed=False 时调用方应 raise 429；count 是当前窗口内累计失败次数，
    retry_after_seconds 是窗口剩余秒数（保守估计取 window，避免泄露已用时长）。
    """

    allowed: bool
    count: int
    retry_after_seconds: int


class LoginRateLimiter:
    def __init__(
        self,
        cache: _CacheLike | None,
        *,
        threshold: int = 5,
        window_seconds: int = 15 * 60,
    ) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        self._cache = cache
        self._threshold = threshold
        self._window_seconds = window_seconds

    @staticmethod
    def _key(ip: str, username: str) -> str:
        # username 长度不一致；用 reasonable 大写归一 + 单冒号分隔即可（仅作 key，不参与展示）
        return f"login:fail:{ip}:{username.lower()}"

    async def register_failure(self, *, ip: str, username: str) -> RateLimitVerdict:
        """每次登录失败调用。返回**调用后**的状态。

        若 cache 不可用：返回 allowed=True，count=0 —— 即不限流。
        """
        if self._cache is None:
            return RateLimitVerdict(allowed=True, count=0, retry_after_seconds=0)
        key = self._key(ip, username)
        count = await self._cache.incr(key, ttl_seconds=self._window_seconds)
        if count >= self._threshold:
            return RateLimitVerdict(
                allowed=False, count=int(count), retry_after_seconds=self._window_seconds,
            )
        return RateLimitVerdict(allowed=True, count=int(count), retry_after_seconds=0)

    async def check(self, *, ip: str, username: str) -> RateLimitVerdict:
        """**调用前**检查；当前累计已到 threshold → 拒绝。

        与 register_failure 的差别：check 不 incr，仅 `get`；可用于在密码验证前
        早早拦截已经触发限流的来源，省一次 argon2id 计算（DoS 防护）。
        """
        if self._cache is None:
            return RateLimitVerdict(allowed=True, count=0, retry_after_seconds=0)
        key = self._key(ip, username)
        raw = await self._cache.get(key)
        count = int(raw) if raw is not None else 0
        if count >= self._threshold:
            return RateLimitVerdict(
                allowed=False, count=count, retry_after_seconds=self._window_seconds,
            )
        return RateLimitVerdict(allowed=True, count=count, retry_after_seconds=0)

    async def reset(self, *, ip: str, username: str) -> None:
        """登录成功后清掉对应计数。"""
        if self._cache is None:
            return
        await self._cache.delete(self._key(ip, username))
