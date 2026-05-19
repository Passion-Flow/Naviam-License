"""License 签发主流程。

最小可跑通版本：纯计算（不依赖 db / object_storage）。
后续接 service 层时把 IssuedLicense 写库 / 推 object_storage / 写 audit log。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from app.core.license.forge_file import ForgeMetadata, pack
from app.core.license.payload import (
    PROTOCOL_VERSION,
    BindingMode,
    LicensePayload,
    Scope,
    SigningAlgorithm,
    VerificationMode,
)
from app.core.signing import get_signer


@dataclass(frozen=True, slots=True)
class IssueLicenseRequest:
    customer_id: str
    product_id: str
    mode: VerificationMode
    scope: Scope
    algorithm: SigningAlgorithm
    binding: BindingMode
    expires_at: datetime
    features: Mapping[str, object]
    limits: Mapping[str, object]
    bound_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.binding == "hard" and not self.bound_fingerprint:
            raise ValueError("binding=='hard' requires bound_fingerprint")


@dataclass(frozen=True, slots=True)
class IssuedLicense:
    license_id: str
    forge_file: bytes               # 打包好的 .forge tarball
    payload: LicensePayload
    metadata: ForgeMetadata


def issue_license(
    req: IssueLicenseRequest,
    *,
    private_key: bytes,
    key_id: str,
    now: datetime | None = None,
) -> IssuedLicense:
    """签发流程。

    1. 构造 LicensePayload（protocol_version / mode / scope / algorithm / binding / expires / features / limits）
    2. 用 signing.<algo>.sign(...) 对规范化字节流签名
    3. 组 ForgeMetadata（algorithm / key_id / signed_at）
    4. 打包 .forge tarball
    5. 返回（外层负责落库 / 推 object_storage / 写 audit log）
    """
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    license_id = str(uuid.uuid4())

    payload = LicensePayload(
        protocol_version=PROTOCOL_VERSION,
        license_id=license_id,
        customer_id=req.customer_id,
        product_id=req.product_id,
        mode=req.mode,
        scope=req.scope,
        binding=req.binding,
        bound_fingerprint=req.bound_fingerprint,
        issued_at=now_utc,
        expires_at=req.expires_at.astimezone(timezone.utc),
        features=dict(req.features),
        limits=dict(req.limits),
    )

    signer = get_signer(req.algorithm)
    signature = signer.sign(
        private_key=private_key,
        key_id=key_id,
        payload=payload.canonical_bytes(),
    )

    metadata = ForgeMetadata(
        algorithm=req.algorithm,
        key_id=key_id,
        signed_at=now_utc,
    )

    forge_bytes = pack(payload, signature.signature, metadata)

    return IssuedLicense(
        license_id=license_id,
        forge_file=forge_bytes,
        payload=payload,
        metadata=metadata,
    )
