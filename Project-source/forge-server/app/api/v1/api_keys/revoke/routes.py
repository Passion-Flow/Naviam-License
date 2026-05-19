"""POST /api/v1/api-keys/{key_id}/revoke —— 吊销 API Key。

仅 Admin Session。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.audit import ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories.api_keys import ApiKeyRepository
from app.state import AppState, get_state

router = APIRouter()


ACTION_APIKEY_REVOKED = "apikey.revoked"


class RevokeApiKeyResponse(BaseModel):
    key_id: str
    status: str


@router.post("/{key_id}/revoke", response_model=RevokeApiKeyResponse)
async def revoke_api_key(
    key_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> RevokeApiKeyResponse:
    if state.api_key_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api key backend not configured",
        )

    repo: ApiKeyRepository = state.api_key_repository  # type: ignore[assignment]
    existing = await repo.get(key_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    if existing.status == "revoked":
        # 幂等：已吊销直接返回（避免重复 audit）
        return RevokeApiKeyResponse(key_id=key_id, status="revoked")

    await repo.revoke(key_id)

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_APIKEY_REVOKED,
        target_type="api_key",
        target_id=key_id,
        payload={
            "customer_id": existing.customer_id,
            "project_label": existing.project_label,
            "key_prefix": existing.key_prefix,
        },
    )

    return RevokeApiKeyResponse(key_id=key_id, status="revoked")
