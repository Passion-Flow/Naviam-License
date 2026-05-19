"""POST /api/v1/licenses/issue — 厂商 Admin 签发 license。

鉴权：Admin Session（优先）或 API Key（fallback，自动化场景）。
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import (
    ACTION_LICENSE_ISSUED,
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
from app.state import AppState, get_state

router = APIRouter()


class IssueLicenseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    product_id: str
    mode: Literal["offline", "hybrid", "online"]
    scope: Literal["customer_x_product", "customer_bundle", "instance"]
    algorithm: Literal["ed25519", "rsa2048", "rsa4096", "sm2"]
    binding: Literal["none", "soft", "hard"]
    expires_at: datetime
    features: dict[str, object] = Field(default_factory=dict)
    limits: dict[str, object] = Field(default_factory=dict)
    bound_fingerprint: str | None = None
    key_id: str | None = None  # 显式指定签名密钥（可选）


class IssueLicenseResponse(BaseModel):
    license_id: str
    forge_file_b64: str
    signing_key_id: str
    algorithm: str
    issued_by: str  # actor 标识（admin:<uid> 或 apikey:<kid>），便于客户排障 / 审计


@router.post("/issue", response_model=IssueLicenseResponse)
async def issue_endpoint(
    body: IssueLicenseBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor: str = Depends(require_admin_or_api_key),
) -> IssueLicenseResponse:
    try:
        req = IssueLicenseRequest(
            customer_id=body.customer_id,
            product_id=body.product_id,
            mode=body.mode,
            scope=body.scope,
            algorithm=body.algorithm,
            binding=body.binding,
            expires_at=body.expires_at,
            features=body.features,
            limits=body.limits,
            bound_fingerprint=body.bound_fingerprint,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    try:
        issued = await issue_license_with_storage(
            storage=state.key_storage,
            req=req,
            key_id=body.key_id,
        )
    except NoActiveKeyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # 持久化（如有 LicenseRepository 注入）
    repo = state.license_repository
    if repo is not None:
        await repo.add_issued(issued)

    # actor 形如 "admin:<uid>" / "apikey:<kid>"
    actor_prefix, _, actor_inner = actor.partition(":")
    actor_type = ACTOR_USER if actor_prefix == "admin" else ACTOR_API_KEY
    audit_payload = {
        "customer_id": body.customer_id,
        "product_id": body.product_id,
        "mode": body.mode,
        "scope": body.scope,
        "algorithm": body.algorithm,
        "binding": body.binding,
        "expires_at": body.expires_at.isoformat(),
        "signing_key_id": issued.metadata.key_id,
    }
    await record_audit(
        state,
        request,
        actor_type=actor_type,
        actor_id=actor_inner or actor,
        action=ACTION_LICENSE_ISSUED,
        target_type="license",
        target_id=issued.license_id,
        payload=audit_payload,
    )
    # 外推业务事件（best-effort；settings.webhook_url 空则 no-op）
    from app.core.webhooks import emit_event
    await emit_event(
        "license.issued",
        {"license_id": issued.license_id, **audit_payload, "actor": actor},
    )

    return IssueLicenseResponse(
        license_id=issued.license_id,
        forge_file_b64=base64.b64encode(issued.forge_file).decode("ascii"),
        signing_key_id=issued.metadata.key_id,
        algorithm=issued.metadata.algorithm,
        issued_by=actor,
    )
