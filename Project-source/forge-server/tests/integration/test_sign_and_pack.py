"""Server-side：生密钥 → 签发 → 解包 → 服务端验签 闭环测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.license.forge_file import FORGE_MAGIC, FORGE_VERSION, unpack
from app.core.license.issuer import IssueLicenseRequest, issue_license
from app.core.signing import get_signer


def test_ed25519_sign_and_pack_roundtrip() -> None:
    signer = get_signer("ed25519")
    kp = signer.generate_keypair()
    assert kp.algorithm == "ed25519"
    assert len(kp.private_key) == 32
    assert len(kp.public_key) == 32

    req = IssueLicenseRequest(
        customer_id="cust-001",
        product_id="prod-naviam",
        mode="hybrid",
        scope="customer_x_product",
        algorithm="ed25519",
        binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        features={"sso": True, "audit_log": True},
        limits={"max_users": 50},
    )

    issued = issue_license(req, private_key=kp.private_key, key_id=kp.key_id)

    # forge_file 是 bytes，可解
    forge = unpack(issued.forge_file)
    assert forge.metadata.magic == FORGE_MAGIC
    assert forge.metadata.forge_version == FORGE_VERSION
    assert forge.metadata.algorithm == "ed25519"
    assert forge.metadata.key_id == kp.key_id
    assert forge.payload.license_id == issued.license_id
    assert forge.payload.customer_id == "cust-001"
    assert forge.payload.product_id == "prod-naviam"
    assert forge.payload.mode == "hybrid"
    assert forge.payload.scope == "customer_x_product"
    assert forge.payload.binding == "none"
    assert forge.payload.features == {"sso": True, "audit_log": True}
    assert forge.payload.limits == {"max_users": 50}

    # 服务端用公钥验签
    assert signer.verify(
        public_key=kp.public_key,
        payload=forge.payload.canonical_bytes(),
        signature=forge.signature,
    )


def test_signature_invalid_when_payload_tampered() -> None:
    signer = get_signer("ed25519")
    kp = signer.generate_keypair()

    req = IssueLicenseRequest(
        customer_id="cust-001",
        product_id="prod",
        mode="offline",
        scope="customer_x_product",
        algorithm="ed25519",
        binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={},
        limits={},
    )
    issued = issue_license(req, private_key=kp.private_key, key_id=kp.key_id)
    forge = unpack(issued.forge_file)

    tampered_payload = forge.payload.canonical_bytes().replace(b"cust-001", b"cust-XXX")
    assert tampered_payload != forge.payload.canonical_bytes()
    assert not signer.verify(
        public_key=kp.public_key,
        payload=tampered_payload,
        signature=forge.signature,
    )


def test_hard_binding_requires_fingerprint() -> None:
    import pytest

    with pytest.raises(ValueError, match="bound_fingerprint"):
        IssueLicenseRequest(
            customer_id="cust-001",
            product_id="prod",
            mode="offline",
            scope="instance",
            algorithm="ed25519",
            binding="hard",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            features={},
            limits={},
        )
