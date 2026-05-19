"""API Key 鉴权 —— Verifier 侧调用 LA 时使用。

Header: X-Forge-API-Key: <plaintext_api_key>

存储模型（in-memory，未来换 DB）：
- 服务端只存 `sha256(plaintext)`；不存明文
- 鉴权时把请求头明文 sha256 后查表

注意：API Key 同时作为心跳 HMAC 的密钥种子（Verifier 持有明文，服务端通过查表+HMAC 校验）。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status

from app.state import AppState, ApiKeyInfo, get_state


API_KEY_HEADER = "X-Forge-API-Key"


def hash_api_key(plaintext: str) -> str:
    """与服务端存储一致的哈希函数。"""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


async def require_api_key(
    state: AppState = Depends(get_state),
    x_forge_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> tuple[ApiKeyInfo, str]:
    """校验 API Key，返回 (ApiKeyInfo, plaintext)。

    顺序：
    1. 先查 in-memory state.api_keys（向后兼容；测试 / 启动注入用）
    2. 若无命中且有 DB-backed auth → 查 DB

    plaintext 透出给路由 → 用于 HMAC 校验（心跳签名）。
    """
    if not x_forge_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing api key",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )
    info: ApiKeyInfo | None = state.api_keys.get(hash_api_key(x_forge_api_key))
    if info is None and state.api_key_auth is not None:
        # DB 查
        info = await state.api_key_auth.lookup(x_forge_api_key)
    if info is None or info.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )
    # 过期边界统一在 middleware 拒绝 —— 防止某个 lookup 路径漏判
    if info.expires_at is not None and info.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="api key expired",
        )
    # 每小时配额（settings.api_key_rate_limit_per_hour > 0 时启用）
    quota = getattr(state, "api_key_quota_limiter", None)
    if quota is not None and quota.enabled:
        allowed, count = await quota.check_and_inc(key_id=info.key_id)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"api key quota exceeded ({count}/{state.settings.api_key_rate_limit_per_hour}/h)",
                headers={"Retry-After": "3600"},
            )
    return info, x_forge_api_key
