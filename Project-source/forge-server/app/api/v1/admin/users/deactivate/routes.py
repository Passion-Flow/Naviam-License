"""POST /api/v1/admin/users/{user_id}/deactivate —— 停用账号（super-only）。

禁止自我停用 —— 防止 super-admin 不小心锁死自己（虽然另一个 super 可以重新激活）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.admin.users._schema import AdminUserResponse
from app.core.audit import ACTION_ADMIN_USER_DEACTIVATED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_super_session
from app.repositories.users import UserRepository
from app.state import AppState, get_state

router = APIRouter()


@router.post("/{user_id}/deactivate", response_model=AdminUserResponse)
async def deactivate_admin_user(
    user_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_super_session),
) -> AdminUserResponse:
    if user_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot deactivate yourself",
        )
    repo: UserRepository = state.user_repository  # type: ignore[assignment]
    user = await repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    await repo.deactivate(user_id)
    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_ADMIN_USER_DEACTIVATED,
        target_type="user",
        target_id=user_id,
        payload={"username": user.username},
    )
    refreshed = await repo.get(user_id)
    return AdminUserResponse.from_model(refreshed)  # type: ignore[arg-type]
