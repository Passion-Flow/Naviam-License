"""GET /api/v1/heartbeats/summary —— 按 license 聚合 + anomaly 判定。

每行：license_id / total_count / distinct_fingerprint_count / last_seen / last_fingerprint / anomaly。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.heartbeats._schema import HeartbeatSummaryEntry
from app.middleware.dual_auth import require_admin_session
from app.repositories.heartbeat_query import HeartbeatQueryRepository
from app.state import AppState, get_state

router = APIRouter()


class HeartbeatSummaryItem(HeartbeatSummaryEntry):
    anomaly: bool
    anomaly_reason: str | None
    threshold: int
    window_seconds: int


class HeartbeatSummaryResponse(BaseModel):
    items: list[HeartbeatSummaryItem]


@router.get("/summary", response_model=HeartbeatSummaryResponse)
async def heartbeat_summary(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    since_seconds: Annotated[int, Query(ge=60, le=30 * 86_400)] = 86_400,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> HeartbeatSummaryResponse:
    if state.heartbeat_query_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="heartbeat backend not configured",
        )
    repo: HeartbeatQueryRepository = state.heartbeat_query_repository  # type: ignore[assignment]

    since = datetime.now(timezone.utc) - timedelta(seconds=since_seconds)
    summaries = await repo.summary_per_license(since=since, limit=limit)

    items: list[HeartbeatSummaryItem] = []
    for s in summaries:
        verdict = await state.multi_env_detector.evaluate(
            s.license_id, collector=state.heartbeat_collector,
        )
        items.append(
            HeartbeatSummaryItem(
                license_id=s.license_id,
                total_count=s.total_count,
                distinct_fingerprint_count=s.distinct_fingerprint_count,
                last_seen_at=s.last_seen_at,
                last_fingerprint=s.last_fingerprint,
                anomaly=verdict.anomaly,
                anomaly_reason=verdict.reason,
                threshold=verdict.threshold,
                window_seconds=verdict.window_seconds,
            )
        )
    return HeartbeatSummaryResponse(items=items)
