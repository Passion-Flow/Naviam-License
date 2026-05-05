"""License 业务服务：签发、续期、吊销。

所有状态变更必须通过本层；View 层只负责序列化与权限校验。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from contracts.signing import IKeySigner
from modules.accounts.models import User
from modules.activations.cloud_id_codec import (
    binding_fingerprint,
    decode as decode_cloud_id,
)
from modules.customers.models import Customer
from modules.products.models import Product

from .codec import (
    LicenseArtifacts,
    encode_activation_code,
    encode_license_envelope,
    encode_license_file,
    encode_license_payload,
)
from .models import License

# 默认 grace = 30 天
DEFAULT_GRACE_SECONDS = 30 * 24 * 3600


def issue_license(
    *,
    product: Product,
    customer: Customer,
    cloud_id_text: str,
    expires_at: datetime,
    issued_by: User,
    signer: IKeySigner,
    notes: str = "",
    not_before: datetime | None = None,
    grace_seconds: int = DEFAULT_GRACE_SECONDS,
) -> tuple[License, LicenseArtifacts]:
    """签发 License。

    返回 (license_instance, LicenseArtifacts(license_file, activation_code))。
    license_file 是 base64url(CBOR(envelope))，可直接写盘为 *.lic 给 SDK 读。
    activation_code 是 base32 分组的人类可读短码，离线粘贴用。
    """
    cloud_id = decode_cloud_id(cloud_id_text)
    product_code = str(cloud_id["product_code"])
    if product_code != product.code:
        raise ValueError(f"cloud_id product_code={product_code} != product.code={product.code}")

    not_before = not_before or timezone.now()
    license_id = _generate_license_id()
    fingerprint = binding_fingerprint(cloud_id)  # 32 字节，去掉 nonce/created_at

    payload = encode_license_payload(
        license_id=license_id,
        product_code=product.code,
        customer_id=str(customer.id),
        cloud_id_binding=fingerprint,
        not_before=int(not_before.timestamp()),
        not_after=int(expires_at.timestamp()),
        grace_seconds=grace_seconds,
        notes=notes,
        signature_kid=signer.kid(),
    )

    signature = signer.sign(payload)
    envelope_bytes = encode_license_envelope(payload, signature, signer.kid())
    artifacts = LicenseArtifacts(
        license_file=encode_license_file(envelope_bytes),
        activation_code=encode_activation_code(envelope_bytes),
    )

    license_obj = License.objects.create(
        license_id=license_id,
        product=product,
        customer=customer,
        cloud_id_binding=fingerprint,           # 32 字节 fingerprint
        cloud_id_text=cloud_id_text,            # 完整文本仅作 audit/排查
        hardware_fp_hash=bytes(cloud_id["hardware_fp"]),
        instance_pubkey=bytes(cloud_id["instance_pubkey_fp"]),
        status=License.STATUS_ISSUED,
        issued_at=timezone.now(),
        not_before=not_before,
        expires_at=expires_at,
        grace_until=expires_at + timedelta(seconds=grace_seconds),
        signature=signature,
        signature_algo="ed25519",
        signature_kid=signer.kid(),
        payload_canonical=payload,
        notes=notes,
        issued_by=issued_by,
    )

    return license_obj, artifacts


def renew_license(
    license_obj: License,
    *,
    new_expires_at: datetime,
    signer: IKeySigner,
    grace_seconds: int = DEFAULT_GRACE_SECONDS,
) -> LicenseArtifacts:
    """续期 License；返回新的 LicenseArtifacts(license_file, activation_code)。"""
    license_obj.expires_at = new_expires_at
    license_obj.grace_until = new_expires_at + timedelta(seconds=grace_seconds)

    # cloud_id_binding 在 issue 时已存为 32 字节 fingerprint；BinaryField 在不同
    # 数据库驱动下可能返回 bytes 或 memoryview — 统一用 bytes() 收敛
    payload = encode_license_payload(
        license_id=license_obj.license_id,
        product_code=license_obj.product.code,
        customer_id=str(license_obj.customer.id),
        cloud_id_binding=bytes(license_obj.cloud_id_binding),
        not_before=int(license_obj.not_before.timestamp()) if license_obj.not_before else 0,
        not_after=int(new_expires_at.timestamp()),
        grace_seconds=grace_seconds,
        notes=license_obj.notes or "",
        signature_kid=signer.kid(),
    )

    signature = signer.sign(payload)
    envelope_bytes = encode_license_envelope(payload, signature, signer.kid())
    artifacts = LicenseArtifacts(
        license_file=encode_license_file(envelope_bytes),
        activation_code=encode_activation_code(envelope_bytes),
    )

    license_obj.signature = signature
    license_obj.signature_kid = signer.kid()
    license_obj.payload_canonical = payload
    license_obj.status = License.STATUS_ISSUED
    license_obj.save(
        update_fields=[
            "expires_at",
            "grace_until",
            "signature",
            "signature_kid",
            "payload_canonical",
            "status",
            "updated_at",
        ]
    )
    return artifacts


def revoke_license(
    license_obj: License,
    *,
    reason: str,
    by_user: User,
) -> None:
    """吊销 License。"""
    license_obj.status = License.STATUS_REVOKED
    license_obj.revoked_at = timezone.now()
    license_obj.revoked_reason = reason
    license_obj.save(update_fields=["status", "revoked_at", "revoked_reason", "updated_at"])


def _generate_license_id() -> str:
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))
