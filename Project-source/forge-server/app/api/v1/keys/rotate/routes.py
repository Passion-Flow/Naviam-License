"""POST /api/v1/keys/{key_id}/rotate —— 轮换密钥（admin only）。

生成同算法新密钥（status=active），把 {key_id} 标记为 rotated。
旧密钥仍能用于**验签**老 license，不能再签发新 license。

仅允许从 active 状态轮换：
- 已 rotated：无意义
- 已 revoked：泄露场景应当 revoke + 不复用，而非轮换
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.v1.keys._schema import KeyResponse
from app.core.audit import ACTION_KEY_GENERATED, ACTION_KEY_ROTATED, ACTOR_USER, record_audit
from app.core.key_storage import KeyStorageError
from app.core.key_storage.rotation import rotate_signing_key
from app.middleware.dual_auth import require_admin_session
from app.state import AppState, get_state

router = APIRouter()


class RotateKeyResponse(BaseModel):
    old_key_id: str
    old_status: str
    new_key: KeyResponse


@router.post("/{key_id}/rotate", response_model=RotateKeyResponse)
async def rotate_key(
    key_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> RotateKeyResponse:
    try:
        old = await state.key_storage.load(key_id)
    except KeyStorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found") from exc

    if old.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"can only rotate active keys (current status: {old.status})",
        )

    new_record = await rotate_signing_key(
        state.key_storage,
        algorithm=old.algorithm,
        previous_key_id=key_id,
    )

    # 两条审计：新建 + 老的 rotated
    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_KEY_GENERATED,
        target_type="signing_key",
        target_id=new_record.key_id,
        payload={
            "algorithm": new_record.algorithm,
            "activate": True,
            "rotated_from": key_id,
        },
    )
    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_KEY_ROTATED,
        target_type="signing_key",
        target_id=key_id,
        payload={"algorithm": old.algorithm, "rotated_into": new_record.key_id},
    )

    return RotateKeyResponse(
        old_key_id=key_id,
        old_status="rotated",
        new_key=KeyResponse.from_record(new_record),
    )
