"""POST /api/v1/auth/change-password —— 当前 admin 改自己的密码。

闭环：
1. 必须带 admin session cookie（require_admin_session）
2. 校验 `current_password` 与本人当前 hash 匹配
3. 校验 `new_password` 满足最小长度（12 字符）—— 卡死默认 `admin@forge.local` 那种短密码
4. 调 `UserRepository.update_password(...)`
5. 销毁本次 session（强制重新登录）
6. 清登录失败计数（reset rate limiter）
7. 写 `auth.password.changed` 审计

`reason` 不存 payload —— 改密本身就是有意义的事件，不需要分类原因。
新密码值绝对不进 audit / response（基础原则）。
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import ACTION_AUTH_PASSWORD_CHANGED, ACTOR_USER, record_audit
from app.core.auth import SessionStore, verify_password
from app.core.auth.rate_limit import LoginRateLimiter
from app.middleware.admin_session import SESSION_COOKIE_NAME
from app.middleware.dual_auth import require_admin_session
from app.repositories.users import UserRepository
from app.state import AppState, get_state

router = APIRouter()

MIN_PASSWORD_LENGTH = 12


class ChangePasswordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=512)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordBody,
    request: Request,
    response: Response,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
    forge_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Response:
    if state.user_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth backends not configured",
        )

    user_repo: UserRepository = state.user_repository  # type: ignore[assignment]
    user = await user_repo.get(actor_id)
    if user is None:
        # session 指的 user_id 在 DB 里没了 —— 视作 401，强制重登
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user gone")

    # 当前密码校验失败一律 401，不带细节（侧信道）
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="current password incorrect",
        )

    # 防呆：禁止新旧同密
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new password must differ from the current one",
        )

    await user_repo.update_password(user.id, new_plaintext=body.new_password)

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=user.id,
        action=ACTION_AUTH_PASSWORD_CHANGED,
        target_type="user",
        target_id=user.id,
        payload={"username": user.username},
    )

    # 销毁本次 session —— 客户端要重新登录（确认新密码工作）
    if forge_session and state.session_store is not None:
        store: SessionStore = state.session_store  # type: ignore[assignment]
        await store.destroy(forge_session)
    response.delete_cookie(SESSION_COOKIE_NAME)

    # 清登录失败计数（避免改完密之后还卡限流）
    limiter: LoginRateLimiter | None = state.login_rate_limiter  # type: ignore[assignment]
    if limiter is not None:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "0.0.0.0"
        )
        await limiter.reset(ip=ip, username=user.username)

    response.status_code = status.HTTP_204_NO_CONTENT
    return response
