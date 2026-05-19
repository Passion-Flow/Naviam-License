"""GET /api/v1/heartbeats/{license_id} —— 单 license 心跳 drill-down + 检测器结论。

包含：
- 最近 N 条心跳记录
- 该 license 历史出现过的所有指纹 + 首次出现时间
- MultiEnvDetector 当前判定（anomaly / threshold / window）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.heartbeats._schema import HeartbeatEntry
from app.middleware.dual_auth import require_admin_session
from app.repositories.heartbeat_query import HeartbeatQueryRepository
from app.state import AppState, get_state

router = APIRouter()


class FingerprintSeen(BaseModel):
    fingerprint: str
    first_seen_at: datetime


class HeartbeatDetectorVerdict(BaseModel):
    anomaly: bool
    distinct_fingerprint_count: int
    threshold: int
    window_seconds: int
    reason: str | None


class LicenseHeartbeatDetail(BaseModel):
    license_id: str
    recent_heartbeats: list[HeartbeatEntry]
    fingerprints_seen: list[FingerprintSeen]
    verdict: HeartbeatDetectorVerdict


@router.get("/{license_id}", response_model=LicenseHeartbeatDetail)
async def heartbeat_detail(
    license_id: str,
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    since_seconds: Annotated[int, Query(ge=60, le=30 * 86_400)] = 86_400,
) -> LicenseHeartbeatDetail:
    if state.heartbeat_query_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="heartbeat backend not configured",
        )
    repo: HeartbeatQueryRepository = state.heartbeat_query_repository  # type: ignore[assignment]
    since = datetime.now(timezone.utc) - timedelta(seconds=since_seconds)

    recent = await repo.list_recent(license_id=license_id, since=since, limit=limit)
    if not recent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no heartbeat records for this license in the window",
        )
    fps = await repo.fingerprints_seen(license_id, since=since)
    verdict = await state.multi_env_detector.evaluate(
        license_id, collector=state.heartbeat_collector,
    )

    return LicenseHeartbeatDetail(
        license_id=license_id,
        recent_heartbeats=[HeartbeatEntry.from_model(r) for r in recent],
        fingerprints_seen=[FingerprintSeen(fingerprint=fp, first_seen_at=fs) for fp, fs in fps],
        verdict=HeartbeatDetectorVerdict(
            anomaly=verdict.anomaly,
            distinct_fingerprint_count=verdict.distinct_fingerprint_count,
            threshold=verdict.threshold,
            window_seconds=verdict.window_seconds,
            reason=verdict.reason,
        ),
    )
