"""Admin Session 优先 + API Key fallback —— 多个 /licenses/* 端点复用。

返回值：actor 字符串 `admin:<uid>` / `apikey:<kid>`，用于审计 + 响应字段。
"""
from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, status

from app.core.auth import SessionExpired, SessionNotFound
from app.middleware.admin_session import SESSION_COOKIE_NAME
from app.middleware.api_key_auth import API_KEY_HEADER, hash_api_key
from app.state import AppState, ApiKeyInfo, get_state


async def require_admin_or_api_key(
    state: AppState = Depends(get_state),
    forge_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    x_forge_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> str:
    """允许两种鉴权之一通过；返回 `admin:<uid>` / `apikey:<kid>`。"""
    if forge_session and state.session_store is not None:
        try:
            data = await state.session_store.load(forge_session)  # type: ignore[union-attr]
            return f"admin:{data.user_id}"
        except (SessionNotFound, SessionExpired):
            pass

    if x_forge_api_key:
        info: ApiKeyInfo | None = state.api_keys.get(hash_api_key(x_forge_api_key))
        if info is None and state.api_key_auth is not None:
            info = await state.api_key_auth.lookup(x_forge_api_key)  # type: ignore[union-attr]
        if info is not None and info.status == "active":
            return f"apikey:{info.key_id}"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="admin session or api key required",
    )


async def require_admin_session(
    state: AppState = Depends(get_state),
    forge_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    """仅 Admin Session（更敏感操作用）；返回 user_id。"""
    if not forge_session or state.session_store is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin session required",
        )
    try:
        data = await state.session_store.load(forge_session)  # type: ignore[union-attr]
    except (SessionNotFound, SessionExpired) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin session required",
        ) from exc
    return data.user_id


async def require_super_session(
    state: AppState = Depends(get_state),
    user_id: str = Depends(require_admin_session),
) -> str:
    """admin session + is_super 双校验；用于 admin/users 这类高危端点。

    返回 super 自己的 user_id（便于审计 actor_id）。
    """
    if state.user_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth backends not configured",
        )
    user = await state.user_repository.get(user_id)  # type: ignore[union-attr]
    if user is None or not user.is_super:
        # 403 而非 401 —— 用户已认证但权限不足
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="super-admin required",
        )
    return user_id
