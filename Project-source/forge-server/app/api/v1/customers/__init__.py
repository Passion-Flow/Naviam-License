"""Customer 资源端点（create / list / detail / update / delete=archive / hard_delete）。"""
from app.api.v1.customers.create import router as create_router
from app.api.v1.customers.delete import router as delete_router
from app.api.v1.customers.detail import router as detail_router
from app.api.v1.customers.hard_delete import router as hard_delete_router
from app.api.v1.customers.list import router as list_router
from app.api.v1.customers.update import router as update_router

__all__ = [
    "create_router",
    "delete_router",
    "detail_router",
    "hard_delete_router",
    "list_router",
    "update_router",
]
