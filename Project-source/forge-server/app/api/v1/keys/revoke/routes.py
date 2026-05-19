"""POST /api/v1/keys/{key_id}/revoke —— 撤销密钥（admin only）。

密钥泄露场景使用：
- 该密钥既不能再签新 license（原本 active 的）
- 也不能再用于**验旧 license**（验签 SDK 应识别 status=revoked）

调用方应该在 revoke 后批量把该密钥签发过的 license 加入 CRL。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.keys._schema import KeyResponse
from app.core.audit import ACTION_KEY_REVOKED, ACTOR_USER, record_audit
from app.core.key_storage import KeyStorageError
from app.core.key_storage.rotation import revoke_signing_key
from app.middleware.dual_auth import require_admin_session
from app.state import AppState, get_state

router = APIRouter()


class RevokeKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=512)


@router.post("/{key_id}/revoke", response_model=KeyResponse)
async def revoke_key(
    key_id: str,
    body: RevokeKeyBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> KeyResponse:
    try:
        existing = await state.key_storage.load(key_id)
    except KeyStorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found") from exc

    if existing.status == "revoked":
        # 幂等：已撤销直接返回，不重复写审计
        return KeyResponse.from_record(existing)

    await revoke_signing_key(state.key_storage, key_id)
    refreshed = await state.key_storage.load(key_id)

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_KEY_REVOKED,
        target_type="signing_key",
        target_id=key_id,
        payload={"algorithm": existing.algorithm, "reason": body.reason},
    )
    return KeyResponse.from_record(refreshed)
