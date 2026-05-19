"""POST /api/v1/licenses/{license_id}/renew —— 续期：基于老 license 签发新 license。

行为：
- 取老 license 的 customer/product/mode/scope/algorithm/binding/bound_fingerprint
- 用新的 expires_at（必填）+ 可选覆盖 features/limits
- 签发一份**全新** license（新 license_id），返回 .forge
- 默认把老 license 加入 CRL（revoke_old=true）—— 防止客户同时持两份

鉴权：Admin Session / API Key 双鉴权（与 issue 一致）。
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import (
    ACTION_LICENSE_ISSUED,
    ACTION_LICENSE_REVOKED,
    ACTOR_API_KEY,
    ACTOR_USER,
    record_audit,
)
from app.core.license.issuer import (
    IssueLicenseRequest,
    NoActiveKeyError,
    issue_license_with_storage,
)
from app.middleware.dual_auth import require_admin_or_api_key
from app.repositories.licenses import LicenseRepository
from app.state import AppState, get_state

router = APIRouter()


class RenewLicenseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: datetime
    features: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None
    revoke_old: bool = Field(default=True)
    reason: str = Field(default="renewed", max_length=512)


class RenewLicenseResponse(BaseModel):
    old_license_id: str
    new_license_id: str
    forge_file_b64: str
    signing_key_id: str
    algorithm: str
    issued_by: str
    old_revoked: bool


def _split_actor(actor: str) -> tuple[str, str]:
    prefix, _, inner = actor.partition(":")
    actor_type = ACTOR_USER if prefix == "admin" else ACTOR_API_KEY
    return actor_type, inner or actor


@router.post("/{license_id}/renew", response_model=RenewLicenseResponse)
async def renew_license(
    license_id: str,
    body: RenewLicenseBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor: str = Depends(require_admin_or_api_key),
) -> RenewLicenseResponse:
    if state.license_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="license backend not configured",
        )

    repo: LicenseRepository = state.license_repository  # type: ignore[assignment]
    old = await repo.get(license_id)
    if old is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="license not found")

    # 续期时不能改 customer/product/mode/scope/algorithm/binding/fingerprint
    try:
        req = IssueLicenseRequest(
            customer_id=old.customer_id,
            product_id=old.product_id,
            mode=old.mode,  # type: ignore[arg-type]
            scope=old.scope,  # type: ignore[arg-type]
            algorithm=old.algorithm,  # type: ignore[arg-type]
            binding=old.binding,  # type: ignore[arg-type]
            expires_at=body.expires_at,
            features=body.features if body.features is not None else (old.features or {}),
            limits=body.limits if body.limits is not None else (old.limits or {}),
            bound_fingerprint=old.bound_fingerprint,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    try:
        issued = await issue_license_with_storage(storage=state.key_storage, req=req)
    except NoActiveKeyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await repo.add_issued(issued)

    actor_type, actor_id = _split_actor(actor)

    # 审计：先记新签发，再记吊销（顺序便于按时间排查）
    await record_audit(
        state,
        request,
        actor_type=actor_type,
        actor_id=actor_id,
        action=ACTION_LICENSE_ISSUED,
        target_type="license",
        target_id=issued.license_id,
        payload={
            "customer_id": old.customer_id,
            "product_id": old.product_id,
            "expires_at": body.expires_at.isoformat(),
            "signing_key_id": issued.metadata.key_id,
            "renewed_from": license_id,
        },
    )

    old_revoked = False
    if body.revoke_old:
        await state.crl_manager.revoke(
            license_id,
            reason=body.reason,
            revoked_by=actor_id if actor_type == ACTOR_USER else None,
        )
        old_revoked = True
        await record_audit(
            state,
            request,
            actor_type=actor_type,
            actor_id=actor_id,
            action=ACTION_LICENSE_REVOKED,
            target_type="license",
            target_id=license_id,
            payload={"reason": body.reason, "renewed_into": issued.license_id},
        )

    return RenewLicenseResponse(
        old_license_id=license_id,
        new_license_id=issued.license_id,
        forge_file_b64=base64.b64encode(issued.forge_file).decode("ascii"),
        signing_key_id=issued.metadata.key_id,
        algorithm=issued.metadata.algorithm,
        issued_by=actor,
        old_revoked=old_revoked,
    )
