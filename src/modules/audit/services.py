"""审计哈希链服务。

每写入一条记录时：
1. 取上一条 hash 作为 prev_hash（链头 = 0x00 * 32）。
2. CBOR canonical 序列化记录内容。
3. hash = SHA-256(prev_hash || canonical_bytes)。
4. 用 audit_key 对 hash 签名。

启动时全链校验由 startup.py 注册的 deploy check 触发：
- 顺序遍历所有 AuditEvent
- 重新计算每一条的 hash 并用 hmac.compare_digest 比对存储值
- 任一记录失配 → 抛 AuditChainCorrupted（部署级 Error.E_AUDIT_CHAIN）

所有哈希比较必须用 hmac.compare_digest（Phase 5 — 防侧信道时序泄露）。
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Iterable

import cbor2
from cryptography.exceptions import InvalidSignature as _CryptoInvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.db import transaction

from contracts.signing import IKeySigner

from .models import AuditEvent

_GENESIS_HASH = b"\x00" * 32


class AuditChainCorrupted(Exception):
    """审计链完整性校验失败。携带具体失配的事件 id 与原因。"""

    def __init__(self, event_id: int | None, reason: str) -> None:
        self.event_id = event_id
        self.reason = reason
        super().__init__(f"audit chain broken at id={event_id}: {reason}")


@dataclass(frozen=True)
class ChainVerifyResult:
    total: int
    last_hash: bytes  # 链尾 hash；启动后可写入运行期监控指标


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


def _recompute_hash(prev_hash: bytes, payload: dict[str, Any]) -> bytes:
    """从持久化的 prev_hash + payload 重算 record_hash；与 append_event 保持一致。"""
    canonical = cbor2.dumps(payload, canonical=True)
    return hashlib.sha256(prev_hash + canonical).digest()


def verify_chain(
    *,
    public_key: Ed25519PublicKey | None = None,
    events: Iterable[AuditEvent] | None = None,
) -> ChainVerifyResult:
    """全链校验。

    - 验 prev_hash 链接（每条 prev_hash 必须 == 上一条 hash，常量时间比对）。
    - 重算每条 hash 并用 hmac.compare_digest 与 DB 中的 hash 比对。
    - 若提供 public_key，对每条 hash 用 Ed25519 验签（kid 暂不分桶；多 kid 支持留 V2）。

    任一失败 → AuditChainCorrupted。

    入参：
      events: 可选，便于注入测试 fixture；默认从 DB 按 id 升序读取。
              生产路径建议分页迭代以避免一次加载海量数据 — 调用方负责分批传入。

    返回 ChainVerifyResult(total, last_hash)。
    """
    iterator = events if events is not None else AuditEvent.objects.order_by("id").iterator()

    expected_prev = _GENESIS_HASH
    total = 0
    last_hash = _GENESIS_HASH

    for event in iterator:
        total += 1
        stored_prev = bytes(event.prev_hash)
        stored_hash = bytes(event.hash)
        stored_sig = bytes(event.signature)

        # 1) 链接校验：当前条 prev_hash 必须 == 上一条 hash（或 genesis）
        if not hmac.compare_digest(stored_prev, expected_prev):
            raise AuditChainCorrupted(event.id, "prev_hash != expected_prev")

        # 2) 完整性：重算 hash 必须 == 存储值
        recomputed = _recompute_hash(stored_prev, event.payload)
        if not hmac.compare_digest(recomputed, stored_hash):
            raise AuditChainCorrupted(event.id, "stored hash != recomputed (payload tampered)")

        # 3) 可选：签名校验
        if public_key is not None:
            try:
                public_key.verify(stored_sig, stored_hash)
            except _CryptoInvalidSignature as exc:
                raise AuditChainCorrupted(event.id, "ed25519 signature invalid") from exc

        expected_prev = stored_hash
        last_hash = stored_hash

    return ChainVerifyResult(total=total, last_hash=last_hash)
