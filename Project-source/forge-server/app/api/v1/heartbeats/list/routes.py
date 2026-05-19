"""GET /api/v1/heartbeats —— 最近心跳列表（admin only）。"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.heartbeats._schema import HeartbeatEntry
from app.middleware.dual_auth import require_admin_session
from app.repositories.heartbeat_query import HeartbeatQueryRepository
from app.state import AppState, get_state

router = APIRouter()


class HeartbeatListResponse(BaseModel):
    items: list[HeartbeatEntry]
    limit: int
    offset: int


@router.get("", response_model=HeartbeatListResponse)
async def list_heartbeats(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    license_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HeartbeatListResponse:
    if state.heartbeat_query_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="heartbeat backend not configured",
        )
    repo: HeartbeatQueryRepository = state.heartbeat_query_repository  # type: ignore[assignment]
    rows = await repo.list_recent(
        license_id=license_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return HeartbeatListResponse(
        items=[HeartbeatEntry.from_model(r) for r in rows],
        limit=limit,
        offset=offset,
    )
