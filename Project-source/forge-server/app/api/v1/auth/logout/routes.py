"""POST /api/v1/auth/logout —— 销毁当前会话。"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.core.audit import ACTION_AUTH_LOGOUT, ACTOR_USER, record_audit
from app.core.auth import SessionExpired, SessionNotFound, SessionStore
from app.middleware.admin_session import SESSION_COOKIE_NAME
from app.state import AppState, get_state

router = APIRouter()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(
    response: Response,
    request: Request,
    state: AppState = Depends(get_state),
    forge_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Response:
    if forge_session and state.session_store is not None:
        store: SessionStore = state.session_store  # type: ignore[assignment]
        # 在销毁前取一次 actor_id（销毁后就拿不到了）
        actor_id: str | None = None
        try:
            data = await store.load(forge_session)
            actor_id = data.user_id
        except (SessionNotFound, SessionExpired):
            pass
        await store.destroy(forge_session)
        if actor_id is not None:
            await record_audit(
                state,
                request,
                actor_type=ACTOR_USER,
                actor_id=actor_id,
                action=ACTION_AUTH_LOGOUT,
                target_type="user",
                target_id=actor_id,
                payload={},
            )
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
