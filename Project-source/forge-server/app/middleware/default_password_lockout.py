"""Default-password strict-mode middleware。

启用条件：settings.auth_block_writes_on_default_password = true。
行为：
- 用 bootstrap_admin_password 登录的 session 在做 **写操作**（POST/PATCH/PUT/DELETE）时，
  除了 `/auth/change-password` / `/auth/logout`，一律拒绝（423 Locked）。
- 强制客户改完密码（自动销毁 session）→ 重登 → flag 清零 → 才能做实事。

不启用时（默认）：什么也不做；仅前端横幅提示（Round AJ）。
"""
from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.core.auth import SessionExpired, SessionNotFound
from app.middleware.admin_session import SESSION_COOKIE_NAME

# 写方法以外都直接放行
_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
# 允许在 default-password 下进行的端点（必须能登出 + 改密）
_ALLOWLIST = {
    "/api/v1/auth/change-password",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
}


class DefaultPasswordLockoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        state = getattr(request.app.state, "forge_state", None)
        if state is None or not state.settings.auth_block_writes_on_default_password:
            return await call_next(request)

        if request.method in _READ_METHODS:
            return await call_next(request)
        if request.url.path in _ALLOWLIST:
            return await call_next(request)
        if state.session_store is None:
            return await call_next(request)

        sid = request.cookies.get(SESSION_COOKIE_NAME)
        if not sid:
            # 没 session → 由后续 auth dependency 自然 401
            return await call_next(request)

        try:
            data = await state.session_store.load(sid)
        except (SessionNotFound, SessionExpired):
            return await call_next(request)

        if data.is_default_password:
            return JSONResponse(
                status_code=423,  # Locked
                content={
                    "detail": "default password in use — change it before performing write operations",
                    "code": "DEFAULT_PASSWORD_LOCKOUT",
                },
            )
        return await call_next(request)
