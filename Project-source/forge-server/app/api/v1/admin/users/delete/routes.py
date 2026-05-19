"""DELETE /api/v1/admin/users/{user_id} —— 硬删除管理员账号。

仅超级管理员可调用。
- 禁止删除自己（避免锁死自己出后台）
- 审计日志保留（append-only），actor_id 引用此用户的日志条目继续保留

与 deactivate 不同：deactivate 把 is_active 置 false 但账号还在；
delete 真的把账号从 users 表里删掉，不可恢复。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.audit import ACTION_ADMIN_USER_DELETED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_super_session
from app.repositories.users import UserRepository
from app.state import AppState, get_state

router = APIRouter()


class DeleteAdminUserResponse(BaseModel):
    user_id: str
    deleted: bool


@router.delete("/{user_id}", response_model=DeleteAdminUserResponse)
async def hard_delete_admin_user(
    user_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_super_session),
) -> DeleteAdminUserResponse:
    if state.user_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="user backend not configured",
        )
    if user_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot delete yourself; use /auth/logout or have another super-admin delete this account",
        )
    repo: UserRepository = state.user_repository  # type: ignore[assignment]
    existing = await repo.get(user_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    ok = await repo.hard_delete(user_id)

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_ADMIN_USER_DELETED,
        target_type="user",
        target_id=user_id,
        payload={"username": existing.username, "email": existing.email, "was_super": existing.is_super},
    )
    return DeleteAdminUserResponse(user_id=user_id, deleted=ok)
