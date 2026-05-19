"""Product 资源 4 按钮端点。"""
from app.api.v1.products.create import router as create_router
from app.api.v1.products.detail import router as detail_router
from app.api.v1.products.list import router as list_router
from app.api.v1.products.update import router as update_router

__all__ = ["create_router", "detail_router", "list_router", "update_router"]
