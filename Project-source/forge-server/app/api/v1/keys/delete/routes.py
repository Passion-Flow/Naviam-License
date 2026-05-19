"""DELETE /api/v1/keys/{key_id} —— 硬删除签名密钥（数据库直删）。

签名密钥的元数据存在 `key_storage` 后端（local_file / object_storage / KMS），
**不是** signing_keys 表。delete 步骤：
1) 找到 key_storage 中的记录（list_ids → load 验证存在）
2) 找出该密钥签发的所有 license_id，并级联删除 license + heartbeat + nonce + revocation
3) 调用 key_storage.delete(key_id) 删除私钥材料
4) 顺便清掉 signing_keys 表里的旧元数据行（如果存在）
5) 写审计

与 revoke 不同：revoke 把状态置 'revoked' 但已签发 license 仍有效；
delete 真的把 signing_key 行删掉，**并级联删除被该密钥签名的所有 license**。
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, select

from app.core.audit import ACTION_KEY_DELETED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.models.heartbeat import HeartbeatLogModel, HeartbeatNonceModel
from app.models.license import LicenseModel
from app.models.revocation import RevocationEntryModel
from app.models.signing_key import SigningKeyModel
from app.state import AppState, get_state

router = APIRouter()
logger = structlog.get_logger("forge.api.keys.delete")


class DeleteSigningKeyResponse(BaseModel):
    key_id: str
    cascaded: dict


@router.delete("/{key_id}", response_model=DeleteSigningKeyResponse)
async def hard_delete_signing_key(
    key_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> DeleteSigningKeyResponse:
    storage = state.key_storage
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="key storage backend not configured",
        )

    # 1) 验证 key 存在于 key_storage
    try:
        record = await storage.load(key_id)
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="signing key not found"
        )

    cascaded: dict[str, int] = {
        "signing_key": 0,
        "license": 0,
        "heartbeat_log": 0,
        "heartbeat_nonce": 0,
        "revocation": 0,
    }

    # 2) DB 级联：删除该密钥签发的全部 license + 心跳/吊销/重放
    db = state.database
    if db is not None:
        async with db.session() as sess:
            license_ids = (
                await sess.execute(
                    select(LicenseModel.license_id).where(
                        LicenseModel.signing_key_id == key_id
                    )
                )
            ).scalars().all()
            if license_ids:
                cascaded["heartbeat_log"] = (
                    await sess.execute(
                        sql_delete(HeartbeatLogModel).where(
                            HeartbeatLogModel.license_id.in_(license_ids)
                        )
                    )
                ).rowcount or 0
                cascaded["heartbeat_nonce"] = (
                    await sess.execute(
                        sql_delete(HeartbeatNonceModel).where(
                            HeartbeatNonceModel.license_id.in_(license_ids)
                        )
                    )
                ).rowcount or 0
                cascaded["revocation"] = (
                    await sess.execute(
                        sql_delete(RevocationEntryModel).where(
                            RevocationEntryModel.license_id.in_(license_ids)
                        )
                    )
                ).rowcount or 0
                cascaded["license"] = (
                    await sess.execute(
                        sql_delete(LicenseModel).where(
                            LicenseModel.license_id.in_(license_ids)
                        )
                    )
                ).rowcount or 0
            # 顺便清掉 signing_keys 表里的旧元数据（如果之前的版本写过）
            await sess.execute(
                sql_delete(SigningKeyModel).where(SigningKeyModel.key_id == key_id)
            )

    # 3) 从 key_storage 后端删除私钥材料
    try:
        await storage.delete(key_id)
        cascaded["signing_key"] = 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("key_storage.delete_failed", key_id=key_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"key_storage delete failed: {exc}",
        )

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_KEY_DELETED,
        target_type="signing_key",
        target_id=key_id,
        payload={"algorithm": record.algorithm, **cascaded},
    )
    return DeleteSigningKeyResponse(key_id=key_id, cascaded=cascaded)
