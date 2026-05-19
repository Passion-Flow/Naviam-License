"""GET /api/v1/api-keys —— 列出所有 API Key（只返回元数据，不返回明文）。

仅 Admin Session。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.middleware.dual_auth import require_admin_session
from app.repositories.api_keys import ApiKeyRepository
from app.state import AppState, get_state

router = APIRouter()


class ApiKeyEntry(BaseModel):
    key_id: str
    key_prefix: str
    customer_id: str
    project_label: str
    status: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime | None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyEntry]
    limit: int
    offset: int


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    customer_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApiKeyListResponse:
    if state.api_key_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api key backend not configured",
        )

    repo: ApiKeyRepository = state.api_key_repository  # type: ignore[assignment]
    rows = await repo.list_all(
        status=status_filter,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )
    items = [
        ApiKeyEntry(
            key_id=r.key_id,
            key_prefix=r.key_prefix,
            customer_id=r.customer_id,
            project_label=r.project_label,
            status=r.status,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
            expires_at=r.expires_at,
        )
        for r in rows
    ]
    return ApiKeyListResponse(items=items, limit=limit, offset=offset)
