"""GET /api/v1/admin/users —— 列出全部 admin 账号。

Admin session 即可访问（非 super），便于团队任何成员看到当前管理员名单。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.v1.admin.users._schema import AdminUserResponse
from app.middleware.dual_auth import require_admin_session
from app.repositories.users import UserRepository
from app.state import AppState, get_state

router = APIRouter()


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]


@router.get("", response_model=AdminUserListResponse)
async def list_admin_users(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
) -> AdminUserListResponse:
    if state.user_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth backends not configured",
        )
    repo: UserRepository = state.user_repository  # type: ignore[assignment]
    users = await repo.list_all()
    return AdminUserListResponse(
        items=[AdminUserResponse.from_model(u) for u in users],
    )
