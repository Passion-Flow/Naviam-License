"""服务端验签（用于 online / hybrid 模式 verifier 回连查询 + LA 后台抽查）。

注意：客户端嵌入的 Verifier SDK 走自己的验签实现（forge-verifier 子产品）；
本模块是 LA **服务端**的验签能力，独立实现。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from app.core.key_storage import KeyStorage, KeyStorageError
from app.core.license.crl.manager import CrlManager
from app.core.license.forge_file import ForgeFileError, unpack
from app.core.signing import get_signer


VerificationStatus = Literal[
    "valid",
    "expired",
    "revoked",
    "binding_mismatch",
    "signature_invalid",
    "unknown_key",
    "malformed",
]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    status: VerificationStatus
    license_id: str | None
    valid_until: datetime | None
    reason: str | None
    server_time: datetime


class _CrlChecker(Protocol):
    async def is_revoked(self, license_id: str) -> bool: ...


async def verify_license(
    *,
    forge_file: bytes,
    key_storage: KeyStorage,
    crl_manager: _CrlChecker | CrlManager,
    deployment_fingerprint: str | None = None,
    now: datetime | None = None,
) -> VerificationResult:
    """权威验签流程。

    步骤：
    1. 解包 .forge tarball → payload + signature + metadata
    2. 查 metadata.key_id → 取公钥
    3. signer.verify() 验签
    4. 查 CRL 是否吊销
    5. 检查 expires_at
    6. binding=hard：比对 bound_fingerprint 与 deployment_fingerprint
    """
    server_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    try:
        forge = unpack(forge_file)
    except ForgeFileError as exc:
        return VerificationResult(
            status="malformed",
            license_id=None,
            valid_until=None,
            reason=str(exc),
            server_time=server_time,
        )

    license_id = forge.payload.license_id
    valid_until = forge.payload.expires_at

    # 取公钥
    try:
        public_key, algorithm = await key_storage.load_public(forge.metadata.key_id)
    except KeyStorageError:
        return VerificationResult(
            status="unknown_key",
            license_id=license_id,
            valid_until=valid_until,
            reason=f"key not found: {forge.metadata.key_id}",
            server_time=server_time,
        )
    if algorithm != forge.metadata.algorithm:
        return VerificationResult(
            status="unknown_key",
            license_id=license_id,
            valid_until=valid_until,
            reason=f"algorithm mismatch: stored={algorithm} forge={forge.metadata.algorithm}",
            server_time=server_time,
        )

    # 验签
    signer = get_signer(forge.metadata.algorithm)  # type: ignore[arg-type]
    ok = signer.verify(
        public_key=public_key,
        payload=forge.payload.canonical_bytes(),
        signature=forge.signature,
    )
    if not ok:
        return VerificationResult(
            status="signature_invalid",
            license_id=license_id,
            valid_until=valid_until,
            reason="signature verification failed",
            server_time=server_time,
        )

    # 吊销检查
    if await crl_manager.is_revoked(license_id):
        return VerificationResult(
            status="revoked",
            license_id=license_id,
            valid_until=valid_until,
            reason="license appears in revocation list",
            server_time=server_time,
        )

    # 过期检查
    expires_utc = forge.payload.expires_at.astimezone(timezone.utc)
    if expires_utc <= server_time:
        return VerificationResult(
            status="expired",
            license_id=license_id,
            valid_until=valid_until,
            reason=f"expired at {expires_utc.isoformat()}",
            server_time=server_time,
        )

    # 硬绑指纹检查
    if forge.payload.binding == "hard":
        bound = forge.payload.bound_fingerprint
        if deployment_fingerprint is None or bound != deployment_fingerprint:
            return VerificationResult(
                status="binding_mismatch",
                license_id=license_id,
                valid_until=valid_until,
                reason="deployment fingerprint does not match bound fingerprint",
                server_time=server_time,
            )

    return VerificationResult(
        status="valid",
        license_id=license_id,
        valid_until=valid_until,
        reason=None,
        server_time=server_time,
    )
