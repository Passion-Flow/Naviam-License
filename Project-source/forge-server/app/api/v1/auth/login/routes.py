"""POST /api/v1/auth/login —— 厂商 Admin 用户名密码登录。"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import (
    ACTION_AUTH_LOGIN_FAILURE,
    ACTION_AUTH_LOGIN_SUCCESS,
    ACTOR_SYSTEM,
    ACTOR_USER,
    record_audit,
)
from app.core.auth import SessionStore, verify_password
from app.core.auth.rate_limit import LoginRateLimiter
from app.middleware.admin_session import SESSION_COOKIE_NAME
from app.repositories.users import UserRepository
from app.state import AppState, get_state


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip() or "0.0.0.0"
    return request.client.host if request.client else "0.0.0.0"

router = APIRouter()


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)


class LoginResponse(BaseModel):
    user_id: str
    username: str
    is_super: bool
    # 客户首次部署后用 `settings.bootstrap_admin_password` 文档密码登录 → True。
    # 前端据此立刻挂横幅催改；改密 + 重登 → 自动归 False。
    is_default_password: bool


@router.post("/login", response_model=LoginResponse)
async def login_endpoint(
    body: LoginBody,
    response: Response,
    request: Request,
    state: AppState = Depends(get_state),
) -> LoginResponse:
    if state.user_repository is None or state.session_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth backends not configured",
        )

    user_repo: UserRepository = state.user_repository  # type: ignore[assignment]
    session_store: SessionStore = state.session_store  # type: ignore[assignment]
    limiter: LoginRateLimiter | None = state.login_rate_limiter  # type: ignore[assignment]
    ip = _client_ip(request)

    # 早拦截 —— 命中限流就不跑 argon2id，避免被当 CPU sink
    if limiter is not None:
        pre = await limiter.check(ip=ip, username=body.username)
        if not pre.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many failed attempts; try again later",
                headers={"Retry-After": str(pre.retry_after_seconds)},
            )

    user = await user_repo.get_by_username(body.username)
    # 通用错误避免侧信道（不告知"用户不存在"vs"密码错"）
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        # 审计：失败原因只内部记录（user_missing / inactive / bad_password），不返回给客户端
        if user is None:
            reason = "user_missing"
        elif not user.is_active:
            reason = "inactive"
        else:
            reason = "bad_password"
        await record_audit(
            state,
            request,
            actor_type=ACTOR_SYSTEM,
            actor_id=body.username,
            action=ACTION_AUTH_LOGIN_FAILURE,
            target_type="user",
            target_id=body.username,
            payload={"reason": reason},
        )
        # 注册失败计数；若本次失败导致越线，立刻 429（而不是 401）让客户端别再试
        if limiter is not None:
            post = await limiter.register_failure(ip=ip, username=body.username)
            if not post.allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="too many failed attempts; try again later",
                    headers={"Retry-After": str(post.retry_after_seconds)},
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    # 常量时间对比 —— 防止 timing leak 默认密码长度。空配置（被显式清掉）永远视为不匹配。
    is_default_password = bool(state.settings.bootstrap_admin_password) and secrets.compare_digest(
        body.password,
        state.settings.bootstrap_admin_password,
    )
    sid, _data = await session_store.create(
        user_id=user.id,
        username=user.username,
        is_default_password=is_default_password,
    )
    await user_repo.mark_login(user.id)
    if limiter is not None:
        # 成功登录清掉对应 (ip, username) 失败计数，避免合法用户撞限
        await limiter.reset(ip=ip, username=body.username)
    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=user.id,
        action=ACTION_AUTH_LOGIN_SUCCESS,
        target_type="user",
        target_id=user.id,
        payload={"username": user.username},
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sid,
        max_age=state.settings.auth_session_max_age_seconds,
        httponly=True,
        samesite="lax",
        # secure=True 在客户私有化 HTTPS 部署时由反代加；此处保留 False 以兼容 dev 启动
        secure=False,
    )
    return LoginResponse(
        user_id=user.id,
        username=user.username,
        is_super=user.is_super,
        is_default_password=is_default_password,
    )
