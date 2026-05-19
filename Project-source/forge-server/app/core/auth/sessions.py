"""Session 管理 —— Redis-backed（用 app.adapters.cache）。

Session ID 是 256-bit 随机串（base64url 编码 ~43 字符）。
Cookie 设置由路由层处理（HttpOnly + Secure + SameSite=Lax）。

Cache key: `forge:session:<sid>` → JSON({user_id, created_at, expires_at})
TTL 由 redis 自管，到期自动清理；refresh 时刷新 TTL。
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.adapters.cache.interface.protocol import Cache


SESSION_KEY_PREFIX = "forge:session:"
USER_SESSIONS_PREFIX = "forge:user_sessions:"  # SET of sids per user_id


class SessionNotFound(Exception):
    """session_id 不存在。"""


class SessionExpired(Exception):
    """session_id 存在但已超期（cache TTL 边界外的二次检查）。"""


def new_session_id() -> str:
    """256-bit 随机 session id，base64url 编码不含填充。"""
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class SessionData:
    user_id: str
    username: str
    created_at: datetime
    expires_at: datetime
    # True 当且仅当本次登录用的是文档化的 `settings.bootstrap_admin_password`。
    # 前端据此挂横幅催改；改密后 session 销毁，下次登录用新密码 → 自动归 False。
    is_default_password: bool = False


class SessionStore:
    """Session 存取统一接口。

    构造时注入 Cache 实例（生产 = RedisCache；测试 = fake RedisCache）。
    """

    def __init__(self, cache: Cache, *, max_age_seconds: int | None = None) -> None:
        # Default comes from settings (HARD RULE 无硬编码) — but callers can
        # override in tests by passing an explicit value.
        from app.settings import get_settings

        self._cache = cache
        self._max_age = (
            max_age_seconds
            if max_age_seconds is not None
            else get_settings().auth_session_max_age_seconds
        )

    def _key(self, sid: str) -> str:
        return f"{SESSION_KEY_PREFIX}{sid}"

    def _user_key(self, user_id: str) -> str:
        return f"{USER_SESSIONS_PREFIX}{user_id}"

    async def create(
        self,
        *,
        user_id: str,
        username: str,
        is_default_password: bool = False,
    ) -> tuple[str, SessionData]:
        sid = new_session_id()
        now = datetime.now(timezone.utc)
        data = SessionData(
            user_id=user_id,
            username=username,
            created_at=now,
            expires_at=now + timedelta(seconds=self._max_age),
            is_default_password=is_default_password,
        )
        await self._cache.set(
            self._key(sid),
            self._serialize(data),
            ttl_seconds=self._max_age,
        )
        # 维护 user_id → sids 索引（list_for_user / revoke 用）
        await self._cache.sadd(self._user_key(user_id), sid, ttl_seconds=self._max_age)
        return sid, data

    async def load(self, sid: str) -> SessionData:
        raw = await self._cache.get(self._key(sid))
        if raw is None:
            raise SessionNotFound("session not found")
        data = self._deserialize(raw)
        if data.expires_at < datetime.now(timezone.utc):
            await self.destroy(sid)
            raise SessionExpired("session expired")
        return data

    async def destroy(self, sid: str) -> None:
        # 顺手从索引里移除（防止 list_for_user 看到僵尸 sid）
        raw = await self._cache.get(self._key(sid))
        if raw is not None:
            try:
                data = self._deserialize(raw)
                await self._cache.srem(self._user_key(data.user_id), sid)
            except Exception:  # noqa: BLE001
                pass  # 索引清理是 best-effort
        await self._cache.delete(self._key(sid))

    async def list_for_user(self, user_id: str) -> list[tuple[str, SessionData]]:
        """活跃 session 列表。索引里的 sid 若 cache 已过期，自动剔除。

        返回 (sid, data) 列表；按 created_at 倒序。
        """
        sids = await self._cache.smembers(self._user_key(user_id))
        result: list[tuple[str, SessionData]] = []
        stale: list[str] = []
        for sid in sids:
            raw = await self._cache.get(self._key(sid))
            if raw is None:
                stale.append(sid)
                continue
            try:
                data = self._deserialize(raw)
                result.append((sid, data))
            except Exception:  # noqa: BLE001
                stale.append(sid)
        if stale:
            await self._cache.srem(self._user_key(user_id), *stale)
        result.sort(key=lambda kv: kv[1].created_at, reverse=True)
        return result

    async def refresh(self, sid: str) -> SessionData:
        """成功调用后将 cache TTL 推回 max_age；用于活跃用户的 sliding session。"""
        data = await self.load(sid)
        now = datetime.now(timezone.utc)
        new_data = SessionData(
            user_id=data.user_id,
            username=data.username,
            created_at=data.created_at,
            expires_at=now + timedelta(seconds=self._max_age),
            is_default_password=data.is_default_password,
        )
        await self._cache.set(self._key(sid), self._serialize(new_data), ttl_seconds=self._max_age)
        return new_data

    @staticmethod
    def _serialize(data: SessionData) -> bytes:
        return json.dumps({
            "user_id": data.user_id,
            "username": data.username,
            "created_at": data.created_at.isoformat(),
            "expires_at": data.expires_at.isoformat(),
            "is_default_password": data.is_default_password,
        }).encode("utf-8")

    @staticmethod
    def _deserialize(raw: bytes) -> SessionData:
        obj = json.loads(raw.decode("utf-8"))
        # 老 session 没这个字段 —— 默认 False 兼容升级
        return SessionData(
            user_id=obj["user_id"],
            username=obj["username"],
            created_at=datetime.fromisoformat(obj["created_at"]),
            expires_at=datetime.fromisoformat(obj["expires_at"]),
            is_default_password=bool(obj.get("is_default_password", False)),
        )
