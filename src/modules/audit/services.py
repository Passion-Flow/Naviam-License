"""审计哈希链服务。

每写入一条记录时：
1. 取上一条 hash 作为 prev_hash（链头 = 0x00 * 32）。
2. CBOR canonical 序列化记录内容。
3. hash = SHA-256(prev_hash || canonical_bytes)。
4. 用 audit_key 对 hash 签名。

启动时全链校验在 startup.py 中触发。
"""
from __future__ import annotations

import hashlib
from typing import Any

import cbor2
from django.db import transaction

from contracts.signing import IKeySigner

from .models import AuditEvent

_GENESIS_HASH = b"\x00" * 32


def append_event(
    *,
    actor_id: str | None,
    actor_name: str | None,
    actor_kind: str,
    actor_ip: str | None,
    action: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    payload: dict[str, Any],
    signer: IKeySigner,
) -> AuditEvent:
    with transaction.atomic():
        last = (
            AuditEvent.objects.order_by("-id")
            .values_list("hash", flat=True)
            .first()
        )
        prev_hash = last if last else _GENESIS_HASH

        record_bytes = cbor2.dumps(payload, canonical=True)
        record_hash = hashlib.sha256(prev_hash + record_bytes).digest()
        signature = signer.sign(record_hash)

        return AuditEvent.objects.create(
            prev_hash=prev_hash,
            hash=record_hash,
            signature=signature,
            signature_kid=signer.kid(),
            actor_id=actor_id,
            actor_name=actor_name,
            actor_kind=actor_kind,
            actor_ip=actor_ip,
            action=action,
            target_kind=target_kind,
            target_id=target_id,
            request_id=request_id,
            payload=payload,
        )
