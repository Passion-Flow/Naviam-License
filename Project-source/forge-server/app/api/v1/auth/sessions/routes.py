"""GET  /api/v1/auth/sessions       —— 列出当前用户所有活跃 session。
DELETE /api/v1/auth/sessions/{sid}  —— 远程踢掉指定 session（自己当前那条要走 logout）。

只看 / 只管自己的 session；不允许跨用户操作（即使 super-admin 也不行 —— 走 /admin/users 重置密码）。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Path, status
from pydantic import BaseModel

from app.core.auth import SessionStore
from app.middleware.admin_session import SESSION_COOKIE_NAME, AdminPrincipal, require_admin_session
from app.state import AppState, get_state

router = APIRouter()


class SessionEntry(BaseModel):
    sid_prefix: str  # 前 8 char；完整 SID 不回前端避免 cookie 窃取
    created_at: datetime
    expires_at: datetime
    is_current: bool


class SessionListResponse(BaseModel):
    items: list[SessionEntry]


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    principal: AdminPrincipal = Depends(require_admin_session),
    state: AppState = Depends(get_state),
    forge_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> SessionListResponse:
    if state.session_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="session backend not configured",
        )
    store: SessionStore = state.session_store  # type: ignore[assignment]
    rows = await store.list_for_user(principal.user_id)
    items = [
        SessionEntry(
            sid_prefix=sid[:8],
            created_at=data.created_at,
            expires_at=data.expires_at,
            is_current=(forge_session == sid),
        )
        for sid, data in rows
    ]
    return SessionListResponse(items=items)


@router.delete("/sessions/{sid_prefix}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    sid_prefix: str = Path(min_length=8, max_length=8),
    principal: AdminPrincipal = Depends(require_admin_session),
    state: AppState = Depends(get_state),
    forge_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> None:
    """按 sid 前缀踢出自己的 session（不允许踢自己当前那条 —— 用 logout）。"""
    if state.session_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="session backend not configured",
        )
    store: SessionStore = state.session_store  # type: ignore[assignment]
    rows = await store.list_for_user(principal.user_id)
    match = next((sid for sid, _ in rows if sid.startswith(sid_prefix)), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    if forge_session == match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot revoke the current session — use /logout instead",
        )
    await store.destroy(match)
