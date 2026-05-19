"""GET /api/v1/auth/me —— 返回当前 admin 信息（鉴权探针）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.admin_session import AdminPrincipal, require_admin_session
from app.state import AppState, get_state

router = APIRouter()


class MeResponse(BaseModel):
    user_id: str
    username: str
    # super-admin 角色标志（前端 Admin team 页据此决定是否显示 Add admin 等操作）
    is_super: bool
    # 当前 session 是否用文档化默认密码登录的 —— 前端据此挂横幅催改
    is_default_password: bool


@router.get("/me", response_model=MeResponse)
async def me_endpoint(
    principal: AdminPrincipal = Depends(require_admin_session),
    state: AppState = Depends(get_state),
) -> MeResponse:
    is_super = False
    if state.user_repository is not None:
        user = await state.user_repository.get(principal.user_id)  # type: ignore[union-attr]
        is_super = bool(user and getattr(user, "is_super", False))
    return MeResponse(
        user_id=principal.user_id,
        username=principal.username,
        is_super=is_super,
        is_default_password=principal.is_default_password,
    )
