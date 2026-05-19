"""GET /api/v1/audit —— 审计日志查询（仅 admin session）。

API Key 不允许查审计（防止 verifier 端拉运营数据）。
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.middleware.dual_auth import require_admin_session
from app.repositories.audit import AuditLogRepository
from app.state import AppState, get_state

router = APIRouter()


class AuditLogEntry(BaseModel):
    id: int
    actor_type: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    payload: dict
    request_id: str | None
    client_ip: str | None
    user_agent: str | None
    occurred_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    limit: int
    offset: int


@router.get("", response_model=AuditLogListResponse)
async def list_audit(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    actor_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    if state.audit_log_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audit backend not configured",
        )

    repo: AuditLogRepository = state.audit_log_repository  # type: ignore[assignment]
    rows = await repo.list(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    items = [
        AuditLogEntry(
            id=r.id,
            actor_type=r.actor_type,
            actor_id=r.actor_id,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            payload=r.payload or {},
            request_id=r.request_id,
            client_ip=r.client_ip,
            user_agent=r.user_agent,
            occurred_at=r.occurred_at,
        )
        for r in rows
    ]
    return AuditLogListResponse(items=items, limit=limit, offset=offset)


@router.get("/export.csv", response_class=Response)
async def export_audit_csv(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    actor_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50000)] = 10000,
) -> Response:
    """合规导出 —— CSV stream，最多 50000 行/次。

    Payload 字段被 JSON 序列化进单格；调用方在 Excel 里再二次解析。
    """
    if state.audit_log_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audit backend not configured",
        )
    repo: AuditLogRepository = state.audit_log_repository  # type: ignore[assignment]
    rows = await repo.list(
        actor_id=actor_id, action=action, target_type=target_type,
        target_id=target_id, since=since, until=until, limit=limit, offset=0,
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "id", "occurred_at", "actor_type", "actor_id", "action",
        "target_type", "target_id", "client_ip", "request_id", "payload_json",
    ])
    for r in rows:
        w.writerow([
            r.id,
            r.occurred_at.isoformat(),
            r.actor_type,
            r.actor_id,
            r.action,
            r.target_type,
            r.target_id,
            r.client_ip or "",
            r.request_id or "",
            json.dumps(r.payload or {}, ensure_ascii=False, separators=(",", ":")),
        ])
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM → Excel 自动识别 UTF-8
    fname = f"forge-audit-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
