"""API Key 管理端点。"""
from app.api.v1.api_keys.issue import router as issue_router
from app.api.v1.api_keys.list import router as list_router
from app.api.v1.api_keys.revoke import router as revoke_router

__all__ = ["issue_router", "list_router", "revoke_router"]
