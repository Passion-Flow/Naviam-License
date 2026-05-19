"""GET /api/v1/licenses/{license_id} —— license 详情 + 吊销状态。

仅 Admin Session（防止 verifier 端拉运营数据）。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.middleware.dual_auth import require_admin_session
from app.repositories.licenses import LicenseRepository
from app.state import AppState, get_state

router = APIRouter()


class LicenseDetailResponse(BaseModel):
    license_id: str
    customer_id: str
    product_id: str
    mode: str
    scope: str
    algorithm: str
    binding: str
    bound_fingerprint: str | None
    signing_key_id: str
    issued_at: datetime
    expires_at: datetime
    features: dict
    limits: dict
    notes: str
    revoked: bool


@router.get("/{license_id}", response_model=LicenseDetailResponse)
async def license_detail(
    license_id: str,
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
) -> LicenseDetailResponse:
    if state.license_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="license backend not configured",
        )
    repo: LicenseRepository = state.license_repository  # type: ignore[assignment]
    row = await repo.get(license_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="license not found")

    revoked = await state.crl_manager.is_revoked(license_id)

    return LicenseDetailResponse(
        license_id=row.license_id,
        customer_id=row.customer_id,
        product_id=row.product_id,
        mode=row.mode,
        scope=row.scope,
        algorithm=row.algorithm,
        binding=row.binding,
        bound_fingerprint=row.bound_fingerprint,
        signing_key_id=row.signing_key_id,
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        features=row.features or {},
        limits=row.limits or {},
        notes=row.notes or "",
        revoked=revoked,
    )
