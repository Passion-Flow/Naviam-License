"""DELETE /api/v1/api-keys/{key_id} —— 硬删除 API Key（数据库直删）。

与 revoke 不同：revoke 把 status 置 'revoked' 但行还在；
delete 真的把 api_key 行删掉。heartbeat 记录里的 api_key_id 字段是 nullable
元数据，会被置空保留（心跳本身不删）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.audit import ACTION_APIKEY_DELETED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories.api_keys import ApiKeyRepository
from app.state import AppState, get_state

router = APIRouter()


class DeleteApiKeyResponse(BaseModel):
    key_id: str
    deleted: bool


@router.delete("/{key_id}", response_model=DeleteApiKeyResponse)
async def hard_delete_api_key(
    key_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> DeleteApiKeyResponse:
    if state.api_key_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api key backend not configured",
        )
    repo: ApiKeyRepository = state.api_key_repository  # type: ignore[assignment]
    existing = await repo.get(key_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    ok = await repo.hard_delete(key_id)

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_APIKEY_DELETED,
        target_type="api_key",
        target_id=key_id,
        payload={
            "customer_id": existing.customer_id,
            "project_label": existing.project_label,
            "key_prefix": existing.key_prefix,
        },
    )
    return DeleteApiKeyResponse(key_id=key_id, deleted=ok)
