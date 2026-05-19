"""POST /api/v1/licenses/verify —— 服务端权威验签。

输入：base64 编码的 .forge 文件 + 可选 deployment_fingerprint。
输出：VerificationResult。

鉴权：Admin Session / API Key 双鉴权（verifier SDK 也用这个端点回连查询）。
"""
from __future__ import annotations

import base64
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.license.verifier import verify_license
from app.middleware.dual_auth import require_admin_or_api_key
from app.state import AppState, get_state

router = APIRouter()


class VerifyLicenseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forge_file_b64: str = Field(min_length=1)
    deployment_fingerprint: str | None = None


class VerifyLicenseResponse(BaseModel):
    status: str
    license_id: str | None
    valid_until: datetime | None
    reason: str | None
    server_time: datetime


@router.post("/verify", response_model=VerifyLicenseResponse)
async def verify_endpoint(
    body: VerifyLicenseBody,
    state: AppState = Depends(get_state),
    _actor: str = Depends(require_admin_or_api_key),
) -> VerifyLicenseResponse:
    try:
        forge_bytes = base64.b64decode(body.forge_file_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"forge_file_b64 must be valid base64: {exc}",
        ) from exc

    result = await verify_license(
        forge_file=forge_bytes,
        key_storage=state.key_storage,
        crl_manager=state.crl_manager,
        deployment_fingerprint=body.deployment_fingerprint,
    )
    return VerifyLicenseResponse(
        status=result.status,
        license_id=result.license_id,
        valid_until=result.valid_until,
        reason=result.reason,
        server_time=result.server_time,
    )
