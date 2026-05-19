"""POST /api/v1/licenses/{license_id}/revoke —— 吊销 license。
POST /api/v1/licenses/{license_id}/unrevoke —— 撤销吊销。

鉴权：Admin Session 优先 / API Key fallback（与 issue 一致）。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import (
    ACTION_LICENSE_REVOKED,
    ACTOR_API_KEY,
    ACTOR_USER,
    record_audit,
)
from app.middleware.dual_auth import require_admin_or_api_key
from app.state import AppState, get_state

router = APIRouter()


ACTION_LICENSE_UNREVOKED = "license.unrevoked"


class RevokeLicenseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=512)


class RevokeLicenseResponse(BaseModel):
    license_id: str
    revoked: bool
    revoked_at: datetime
    reason: str
    revoked_by: str


def _split_actor(actor: str) -> tuple[str, str]:
    """`admin:<uid>` / `apikey:<kid>` → (actor_type, actor_id)。"""
    prefix, _, inner = actor.partition(":")
    actor_type = ACTOR_USER if prefix == "admin" else ACTOR_API_KEY
    return actor_type, inner or actor


@router.post("/{license_id}/revoke", response_model=RevokeLicenseResponse)
async def revoke_license(
    license_id: str,
    body: RevokeLicenseBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor: str = Depends(require_admin_or_api_key),
) -> RevokeLicenseResponse:
    actor_type, actor_id = _split_actor(actor)

    # 如果有 LicenseRepository 注入，校验 license 存在（防止吊销不存在的 ID）
    repo = state.license_repository
    if repo is not None:
        license_row = await repo.get(license_id)  # type: ignore[union-attr]
        if license_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="license not found",
            )

    now = datetime.now(timezone.utc)
    await state.crl_manager.revoke(
        license_id,
        reason=body.reason,
        revoked_by=actor_id if actor_type == ACTOR_USER else None,
    )

    await record_audit(
        state,
        request,
        actor_type=actor_type,
        actor_id=actor_id,
        action=ACTION_LICENSE_REVOKED,
        target_type="license",
        target_id=license_id,
        payload={"reason": body.reason},
    )
    from app.core.webhooks import emit_event
    await emit_event(
        "license.revoked",
        {"license_id": license_id, "reason": body.reason, "actor": actor},
    )

    return RevokeLicenseResponse(
        license_id=license_id,
        revoked=True,
        revoked_at=now,
        reason=body.reason,
        revoked_by=actor,
    )


class UnrevokeLicenseResponse(BaseModel):
    license_id: str
    revoked: bool


@router.post("/{license_id}/unrevoke", response_model=UnrevokeLicenseResponse)
async def unrevoke_license(
    license_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor: str = Depends(require_admin_or_api_key),
) -> UnrevokeLicenseResponse:
    actor_type, actor_id = _split_actor(actor)

    was_revoked = await state.crl_manager.is_revoked(license_id)
    if not was_revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="license not in revocation list",
        )

    await state.crl_manager.unrevoke(license_id)

    await record_audit(
        state,
        request,
        actor_type=actor_type,
        actor_id=actor_id,
        action=ACTION_LICENSE_UNREVOKED,
        target_type="license",
        target_id=license_id,
        payload={},
    )

    return UnrevokeLicenseResponse(license_id=license_id, revoked=False)
