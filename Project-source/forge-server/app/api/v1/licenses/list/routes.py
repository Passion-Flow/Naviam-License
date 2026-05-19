"""GET /api/v1/licenses —— 列出 license（admin only）。

list 不返回完整 features/limits/notes 详情，只回元数据；详情走 /licenses/{id}。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.middleware.dual_auth import require_admin_session
from app.repositories.licenses import LicenseRepository
from app.state import AppState, get_state

router = APIRouter()


class LicenseSummary(BaseModel):
    license_id: str
    customer_id: str
    product_id: str
    mode: str
    scope: str
    algorithm: str
    binding: str
    signing_key_id: str
    issued_at: datetime
    expires_at: datetime
    is_revoked: bool


class LicenseListResponse(BaseModel):
    items: list[LicenseSummary]
    limit: int
    offset: int


@router.get("", response_model=LicenseListResponse)
async def list_licenses(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    customer_id: Annotated[str | None, Query()] = None,
    product_id: Annotated[str | None, Query()] = None,
    mode: Annotated[str | None, Query()] = None,
    algorithm: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(description="license_id substring search (case-insensitive)")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LicenseListResponse:
    if state.license_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="license backend not configured",
        )
    repo: LicenseRepository = state.license_repository  # type: ignore[assignment]
    rows = await repo.list(
        customer_id=customer_id,
        product_id=product_id,
        mode=mode,
        algorithm=algorithm,
        q=q,
        limit=limit,
        offset=offset,
    )
    # 一次性拉所有吊销 ID 转 set，避免 N+1
    revoked_ids: set[str] = set()
    if state.revocation_store is not None:
        revoked_ids = {e.license_id for e in await state.revocation_store.list_entries()}
    items = [
        LicenseSummary(
            license_id=r.license_id,
            customer_id=r.customer_id,
            product_id=r.product_id,
            mode=r.mode,
            scope=r.scope,
            algorithm=r.algorithm,
            binding=r.binding,
            signing_key_id=r.signing_key_id,
            issued_at=r.issued_at,
            expires_at=r.expires_at,
            is_revoked=r.license_id in revoked_ids,
        )
        for r in rows
    ]
    return LicenseListResponse(items=items, limit=limit, offset=offset)
