"""密钥轮换 helper。

策略（与 .agent.md 中"密钥服务启动时一次性加载到内存"+"支持密钥轮换"对齐）：
- 当前 active 密钥用于**签新 license**
- 旧密钥 status=rotated 后仅保留用于**验旧 license**
- revoked 状态的密钥两者皆不能（验旧 license 也 fail；通常是密钥泄露场景）

调用顺序：
    storage = get_key_storage()
    new_record = await rotate_signing_key(
        storage,
        algorithm="ed25519",
        previous_key_id="ed25519-abc",
    )
    # 此后：
    #   - 新签发用 new_record.key_id
    #   - 老 license 用 previous_key_id 验签仍能通过
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.key_storage.interface import KeyRecord, KeyStorage
from app.core.signing import get_signer


async def generate_and_save_signing_key(
    storage: KeyStorage,
    *,
    algorithm: str,
    activate: bool = True,
) -> KeyRecord:
    """生成新密钥对 + 落库。"""
    signer = get_signer(algorithm)
    keypair = signer.generate_keypair()

    now = datetime.now(timezone.utc)
    record = KeyRecord(
        key_id=keypair.key_id,
        algorithm=keypair.algorithm,
        public_key=keypair.public_key,
        private_key=keypair.private_key,
        status="active" if activate else "rotated",
        created_at=now,
        activated_at=now if activate else None,
    )
    await storage.save(record)
    return record


async def rotate_signing_key(
    storage: KeyStorage,
    *,
    algorithm: str,
    previous_key_id: str | None = None,
) -> KeyRecord:
    """生成新密钥；把上一把 active 密钥状态置为 rotated。

    新密钥 status=active。
    旧密钥可继续验签（保留私钥密文，仅 status 改）。
    """
    new_record = await generate_and_save_signing_key(storage, algorithm=algorithm, activate=True)
    if previous_key_id:
        await storage.update_status(previous_key_id, "rotated")
    return new_record


async def revoke_signing_key(storage: KeyStorage, key_id: str) -> None:
    """密钥泄露时使用。被 revoked 的密钥签发过的 license 应批量进入 CRL。"""
    await storage.update_status(key_id, "revoked")


def _short_id() -> str:
    return uuid.uuid4().hex[:12]
