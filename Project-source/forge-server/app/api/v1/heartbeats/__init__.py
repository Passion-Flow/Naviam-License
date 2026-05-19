"""Heartbeat 监控端点（admin only）。"""
from app.api.v1.heartbeats.detail import router as detail_router
from app.api.v1.heartbeats.list import router as list_router
from app.api.v1.heartbeats.summary import router as summary_router

__all__ = ["detail_router", "list_router", "summary_router"]
