"""Auth 端点聚合点。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth.change_password import router as change_password_router
from app.api.v1.auth.login import router as login_router
from app.api.v1.auth.logout import router as logout_router
from app.api.v1.auth.me import router as me_router
from app.api.v1.auth.sessions import router as sessions_router

router = APIRouter()
router.include_router(login_router)
router.include_router(logout_router)
router.include_router(me_router)
router.include_router(change_password_router)
router.include_router(sessions_router)
