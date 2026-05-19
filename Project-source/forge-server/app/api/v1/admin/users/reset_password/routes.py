"""POST /api/v1/admin/users/{user_id}/reset-password —— super 给同事强制改密。

与 `/auth/change-password` 的差别：
- 那里：用户自己改自己（需 current_password）
- 这里：super 把同事密码改了（不需要 current_password，但**禁止改自己**走这条；自己改密用 change-password）

为什么禁止自己走 reset-password 路径：避免 super 被诱骗到一个简化路径绕开"需要当前密码"的校验。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.admin.users._schema import AdminUserResponse
from app.core.audit import ACTION_ADMIN_USER_PASSWORD_RESET, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_super_session
from app.repositories.users import UserRepository
from app.state import AppState, get_state

router = APIRouter()


class ResetPasswordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=12, max_length=512)


@router.post("/{user_id}/reset-password", response_model=AdminUserResponse)
async def reset_admin_user_password(
    user_id: str,
    body: ResetPasswordBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_super_session),
) -> AdminUserResponse:
    if user_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="use /auth/change-password to change your own password",
        )
    repo: UserRepository = state.user_repository  # type: ignore[assignment]
    user = await repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    await repo.update_password(user_id, new_plaintext=body.new_password)
    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_ADMIN_USER_PASSWORD_RESET,
        target_type="user",
        target_id=user_id,
        # 新密码值绝不写 payload
        payload={"username": user.username},
    )
    refreshed = await repo.get(user_id)
    return AdminUserResponse.from_model(refreshed)  # type: ignore[arg-type]
