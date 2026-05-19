"""POST /api/v1/admin/users —— 创建新 admin 账号（super-only）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.admin.users._schema import AdminUserResponse
from app.core.audit import ACTION_ADMIN_USER_CREATED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_super_session
from app.repositories.users import UserRepository
from app.state import AppState, get_state

router = APIRouter()


class CreateAdminUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    # 轻量 email 校验 —— 不靠 pydantic[email] extra（避免增加部署依赖）
    email: str = Field(min_length=3, max_length=256, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=512)
    is_super: bool = False


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    body: CreateAdminUserBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_super_session),
) -> AdminUserResponse:
    if state.user_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth backends not configured",
        )
    repo: UserRepository = state.user_repository  # type: ignore[assignment]

    # username / email 唯一性 —— 提前查避免依赖 DB 异常做控制流
    if await repo.get_by_username(body.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"username already exists: {body.username}",
        )
    if await repo.get_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already exists",
        )

    user = await repo.create(
        username=body.username,
        email=body.email,
        plaintext_password=body.password,
        is_super=body.is_super,
    )

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_ADMIN_USER_CREATED,
        target_type="user",
        target_id=user.id,
        # 永远不在 payload 里写密码，连长度都不写（防侧信道）
        payload={"username": user.username, "email": user.email, "is_super": user.is_super},
    )
    return AdminUserResponse.from_model(user)
