"""Admin Session 鉴权 —— 厂商 Admin 登录后用。

Cookie 名：`forge_session`（HttpOnly + SameSite=Lax + 客户私有化场景下可 Secure）
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, status

from app.core.auth import SessionData, SessionExpired, SessionNotFound, SessionStore
from app.state import AppState, get_state


SESSION_COOKIE_NAME = "forge_session"


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    """认证后的 Admin 上下文。"""

    user_id: str
    username: str
    is_default_password: bool = False


async def require_admin_session(
    state: AppState = Depends(get_state),
    forge_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AdminPrincipal:
    if not forge_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    if state.session_store is None:
        # 未注入 SessionStore（如 app 还在裸 in-memory 模式）→ 拒绝
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session backend not configured",
        )
    store: SessionStore = state.session_store  # type: ignore[assignment]
    try:
        data: SessionData = await store.load(forge_session)
    except (SessionNotFound, SessionExpired):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
        )
    return AdminPrincipal(
        user_id=data.user_id,
        username=data.username,
        is_default_password=data.is_default_password,
    )
