"""Admin team management endpoints. Each button is its own subdir per project rule."""
from app.api.v1.admin.users.create import router as create_router
from app.api.v1.admin.users.deactivate import router as deactivate_router
from app.api.v1.admin.users.list import router as list_router
from app.api.v1.admin.users.reactivate import router as reactivate_router
from app.api.v1.admin.users.reset_password import router as reset_password_router

__all__ = [
    "create_router",
    "deactivate_router",
    "list_router",
    "reactivate_router",
    "reset_password_router",
]
