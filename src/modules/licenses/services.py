"""License 业务服务：签发、续期、吊销。

所有状态变更必须通过本层；View 层只负责序列化与权限校验。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from contracts.signing import IKeySigner
from modules.accounts.models import User
from modules.activations.cloud_id_codec import decode as decode_cloud_id
from modules.customers.models import Customer
from modules.products.models import Product

from .codec import encode_activation_code, encode_license_file, encode_license_payload
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
) -> tuple[License, str]:
    """签发 License。

    返回 (license_instance, activation_code_text)。
    """
    cloud_id = decode_cloud_id(cloud_id_text)
    product_code = str(cloud_id["product_code"])
    if product_code != product.code:
        raise ValueError(f"cloud_id product_code={product_code} != product.code={product.code}")

    not_before = not_before or timezone.now()
    license_id = _generate_license_id()

    payload = encode_license_payload(
        license_id=license_id,
        product_code=product.code,
        customer_id=str(customer.id),
        cloud_id_binding=bytes(cloud_id_text, "utf-8"),
        not_before=int(not_before.timestamp()),
        not_after=int(expires_at.timestamp()),
        grace_seconds=grace_seconds,
        notes=notes,
        signature_kid=signer.kid(),
    )

    signature = signer.sign(payload)
    license_file = encode_license_file(payload, signature, signer.kid())
    activation_code = encode_activation_code(license_file)

    license_obj = License.objects.create(
        license_id=license_id,
        product=product,
        customer=customer,
        cloud_id_binding=bytes(cloud_id_text, "utf-8"),
        cloud_id_text=cloud_id_text,
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

    return license_obj, activation_code


def renew_license(
    license_obj: License,
    *,
    new_expires_at: datetime,
    signer: IKeySigner,
    grace_seconds: int = DEFAULT_GRACE_SECONDS,
) -> str:
    """续期 License；返回新的 Activation Code。"""
    license_obj.expires_at = new_expires_at
    license_obj.grace_until = new_expires_at + timedelta(seconds=grace_seconds)

    payload = encode_license_payload(
        license_id=license_obj.license_id,
        product_code=license_obj.product.code,
        customer_id=str(license_obj.customer.id),
        cloud_id_binding=license_obj.cloud_id_binding,
        not_before=int(license_obj.not_before.timestamp()) if license_obj.not_before else 0,
        not_after=int(new_expires_at.timestamp()),
        grace_seconds=grace_seconds,
        notes=license_obj.notes or "",
        signature_kid=signer.kid(),
    )

    signature = signer.sign(payload)
    license_file = encode_license_file(payload, signature, signer.kid())
    activation_code = encode_activation_code(license_file)

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
    return activation_code


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
