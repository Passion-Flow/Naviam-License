"""Verifier 端到端：直接构造 .forge tar 包，喂给 Verifier.verify_blocking。

注意：本测试在 verifier 侧**重新构造** .forge 字节流（不 import forge-server），
保证 verifier 仓库可独立运行测试，不依赖 server 包。
"""
from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from forge_verifier import Verifier, VerificationFailed


def _build_payload_bytes(
    *,
    license_id: str = "lic-test",
    customer_id: str = "cust-001",
    product_id: str = "prod",
    mode: str = "offline",
    scope: str = "customer_x_product",
    binding: str = "none",
    issued_at: datetime,
    expires_at: datetime,
    features: Mapping[str, object] | None = None,
    limits: Mapping[str, object] | None = None,
) -> bytes:
    payload = {
        "protocol_version": "1.0",
        "license_id": license_id,
        "customer_id": customer_id,
        "product_id": product_id,
        "mode": mode,
        "scope": scope,
        "binding": binding,
        "bound_fingerprint": None,
        "issued_at": issued_at.astimezone(timezone.utc).isoformat(),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "features": dict(features or {}),
        "limits": dict(limits or {}),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _build_forge_tar(payload_bytes: bytes, signature: bytes, metadata: dict[str, object]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in [
            ("payload.json", payload_bytes),
            ("signature.bin", signature),
            ("metadata.json", json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")),
        ]:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _sign_and_build(payload_bytes: bytes, algorithm: str = "ed25519") -> tuple[bytes, bytes]:
    """返回 (forge_file_bytes, public_key_bytes)。"""
    sk = Ed25519PrivateKey.generate()
    raw_private = sk.private_bytes_raw()
    raw_public = sk.public_key().public_bytes_raw()
    sig = sk.sign(payload_bytes)

    metadata = {
        "magic": "forg",
        "forge_version": "1.0",
        "algorithm": algorithm,
        "key_id": "ed25519-test",
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }
    forge_bytes = _build_forge_tar(payload_bytes, sig, metadata)
    return forge_bytes, raw_public


def test_verify_blocking_valid(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    payload_bytes = _build_payload_bytes(
        issued_at=now,
        expires_at=now + timedelta(days=365),
        features={"sso": True},
    )
    forge_bytes, public_key = _sign_and_build(payload_bytes)

    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=public_key,
        mode="offline",
    )
    result = verifier.verify_blocking()
    assert result.status == "valid"
    assert result.license_id == "lic-test"
    assert result.features == {"sso": True}


def test_verify_blocking_expired(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    payload_bytes = _build_payload_bytes(
        issued_at=now - timedelta(days=400),
        expires_at=now - timedelta(days=1),
    )
    forge_bytes, public_key = _sign_and_build(payload_bytes)

    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=public_key,
        mode="offline",
    )
    with pytest.raises(VerificationFailed) as exc_info:
        verifier.verify_blocking()
    assert exc_info.value.status == "expired"


def test_verify_blocking_signature_invalid(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    payload_bytes = _build_payload_bytes(
        issued_at=now,
        expires_at=now + timedelta(days=30),
    )
    forge_bytes, public_key = _sign_and_build(payload_bytes)

    # 篡改：替换 payload.json 内的 customer_id，但保持原签名
    tampered = forge_bytes.replace(b"cust-001", b"cust-XXX")
    assert tampered != forge_bytes

    license_path = tmp_path / "license.forge"
    license_path.write_bytes(tampered)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=public_key,
        mode="offline",
    )
    with pytest.raises(VerificationFailed) as exc_info:
        verifier.verify_blocking()
    assert exc_info.value.status == "signature_invalid"


def test_verify_blocking_grace_period(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    payload_bytes = _build_payload_bytes(
        issued_at=now - timedelta(days=400),
        expires_at=now - timedelta(seconds=60),  # 60 秒前过期
    )
    forge_bytes, public_key = _sign_and_build(payload_bytes)

    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=public_key,
        mode="offline",
        grace_period_seconds=3600,  # 1 小时宽限
    )
    result = verifier.verify_blocking()
    assert result.status == "grace_period"
