"""GET /api/v1/health — 健康检查（不鉴权）。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
