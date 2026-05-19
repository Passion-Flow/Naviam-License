"""CRL 端到端（Verifier 侧）：
- 构造一份 license + 一份 CRL，CRL 包含该 license → verify_blocking 抛 revoked
- CRL 不包含该 license → 正常 valid
- CRL 过期 / 篡改 / 缺失 → 按 crl_required 决定行为
"""
from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from forge_verifier import Verifier, VerificationFailed


def _add_tar(buf_tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    buf_tar.addfile(info, io.BytesIO(data))


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _build_license_forge(
    *,
    sk: Ed25519PrivateKey,
    license_id: str = "lic-test",
    expires_in_days: int = 30,
) -> tuple[bytes, bytes]:
    """构造一份 license `.forge`，返回 (forge_bytes, public_key)。"""
    now = datetime.now(timezone.utc)
    payload = {
        "protocol_version": "1.0",
        "license_id": license_id,
        "customer_id": "cust-1",
        "product_id": "prod",
        "mode": "offline",
        "scope": "instance",
        "binding": "none",
        "bound_fingerprint": None,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(days=expires_in_days)).isoformat(),
        "features": {},
        "limits": {},
    }
    payload_bytes = _canonical(payload)
    sig = sk.sign(payload_bytes)
    metadata = {
        "magic": "forg",
        "forge_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "ed25519-test",
        "signed_at": now.isoformat(),
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_tar(tar, "payload.json", payload_bytes)
        _add_tar(tar, "signature.bin", sig)
        _add_tar(tar, "metadata.json", _canonical(metadata))
    return buf.getvalue(), sk.public_key().public_bytes_raw()


def _build_crl(
    *,
    sk: Ed25519PrivateKey,
    revoked_license_ids: list[str],
    next_update_offset_seconds: int = 86400,
    issued_offset_seconds: int = 0,
) -> bytes:
    """构造一份 .crl 文件。"""
    now = datetime.now(timezone.utc) + timedelta(seconds=issued_offset_seconds)
    entries = [
        {"license_id": lid, "revoked_at": now.isoformat(), "reason": "test-revoke"}
        for lid in revoked_license_ids
    ]
    # 与 server 侧一致：entries 按 license_id 排序
    payload = {
        "crl_version": "1.0",
        "sequence": 1,
        "issued_at": now.isoformat(),
        "next_update_at": (now + timedelta(seconds=next_update_offset_seconds)).isoformat(),
        "entries": sorted(entries, key=lambda e: e["license_id"]),
    }
    payload_bytes = _canonical(payload)
    sig = sk.sign(payload_bytes)
    metadata = {
        "magic": "crl",
        "crl_format_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "ed25519-test",
        "signed_at": now.isoformat(),
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_tar(tar, "payload.json", payload_bytes)
        _add_tar(tar, "signature.bin", sig)
        _add_tar(tar, "metadata.json", _canonical(metadata))
    return buf.getvalue()


# ────────────────────────────────────────────────────────────


def test_no_crl_optional_passes(tmp_path: Path) -> None:
    """默认 crl_path=None & crl_required=False → 跳过 CRL 检查，license 仍 valid。"""
    sk = Ed25519PrivateKey.generate()
    forge_bytes, pk = _build_license_forge(sk=sk)
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
    )
    assert verifier.verify_blocking().status == "valid"


def test_no_crl_but_required_fails(tmp_path: Path) -> None:
    """crl_required=True 但没传 crl_path → 拒绝。"""
    sk = Ed25519PrivateKey.generate()
    forge_bytes, pk = _build_license_forge(sk=sk)
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
        crl_required=True,
    )
    with pytest.raises(VerificationFailed) as exc:
        verifier.verify_blocking()
    assert exc.value.status == "revoked"


def test_crl_valid_no_revocation_passes(tmp_path: Path) -> None:
    sk = Ed25519PrivateKey.generate()
    forge_bytes, pk = _build_license_forge(sk=sk, license_id="lic-keep")
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    crl_path = tmp_path / "crl.crl"
    crl_path.write_bytes(_build_crl(sk=sk, revoked_license_ids=["other-lic"]))

    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
        crl_path=crl_path,
        crl_required=True,
    )
    assert verifier.verify_blocking().status == "valid"


def test_crl_revokes_license(tmp_path: Path) -> None:
    sk = Ed25519PrivateKey.generate()
    forge_bytes, pk = _build_license_forge(sk=sk, license_id="lic-leaked")
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    crl_path = tmp_path / "crl.crl"
    crl_path.write_bytes(_build_crl(sk=sk, revoked_license_ids=["lic-leaked"]))

    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
        crl_path=crl_path,
    )
    with pytest.raises(VerificationFailed) as exc:
        verifier.verify_blocking()
    assert exc.value.status == "revoked"
    assert "test-revoke" in (exc.value.reason or "")


def test_crl_expired_with_required_fails(tmp_path: Path) -> None:
    """CRL 已过 next_update_at —— crl_required=True 时拒绝。"""
    sk = Ed25519PrivateKey.generate()
    forge_bytes, pk = _build_license_forge(sk=sk)
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    crl_path = tmp_path / "crl.crl"
    # next_update_at 在过去（-1 小时）→ 已过期
    crl_path.write_bytes(_build_crl(sk=sk, revoked_license_ids=[], next_update_offset_seconds=-3600))

    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
        crl_path=crl_path,
        crl_required=True,
    )
    with pytest.raises(VerificationFailed) as exc:
        verifier.verify_blocking()
    assert exc.value.status == "revoked"
    assert "CRL invalid" in (exc.value.reason or "") or "CRL" in (exc.value.reason or "")


def test_crl_tampered_with_required_fails(tmp_path: Path) -> None:
    sk = Ed25519PrivateKey.generate()
    forge_bytes, pk = _build_license_forge(sk=sk)
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    crl_path = tmp_path / "crl.crl"
    crl_bytes = _build_crl(sk=sk, revoked_license_ids=["something-else"])
    # 篡改 payload.json 内已知字符串：替换 license_id 让 HMAC 无法匹配
    tampered = crl_bytes.replace(b"something-else", b"something-XYZED")
    assert tampered != crl_bytes
    crl_path.write_bytes(tampered)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
        crl_path=crl_path,
        crl_required=True,
    )
    with pytest.raises(VerificationFailed) as exc:
        verifier.verify_blocking()
    assert exc.value.status == "revoked"


def test_crl_signed_by_different_key_fails(tmp_path: Path) -> None:
    """攻击者用自己的密钥签了份"空 CRL"想绕过吊销 → Verifier 用 LA 公钥验签失败。"""
    la_sk = Ed25519PrivateKey.generate()
    attacker_sk = Ed25519PrivateKey.generate()

    forge_bytes, la_pk = _build_license_forge(sk=la_sk, license_id="lic-leaked")
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    # 攻击者签的"空 CRL"
    fake_crl = _build_crl(sk=attacker_sk, revoked_license_ids=[])
    crl_path = tmp_path / "crl.crl"
    crl_path.write_bytes(fake_crl)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=la_pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
        crl_path=crl_path,
        crl_required=True,
    )
    with pytest.raises(VerificationFailed) as exc:
        verifier.verify_blocking()
    assert exc.value.status == "revoked"


def test_crl_signed_by_different_key_optional_continues(tmp_path: Path) -> None:
    """crl_required=False 时无效 CRL 不阻断（默默忽略），license 仍 valid。

    安全权衡：宽松模式下"无效 CRL"被忽略；严格模式必须显式要求 CRL。
    """
    la_sk = Ed25519PrivateKey.generate()
    attacker_sk = Ed25519PrivateKey.generate()

    forge_bytes, la_pk = _build_license_forge(sk=la_sk, license_id="lic-x")
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)

    fake_crl = _build_crl(sk=attacker_sk, revoked_license_ids=["lic-x"])
    crl_path = tmp_path / "crl.crl"
    crl_path.write_bytes(fake_crl)

    verifier = Verifier(
        license_file_path=license_path,
        public_key=la_pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="m",
        crl_path=crl_path,
        crl_required=False,  # 宽松模式
    )
    result = verifier.verify_blocking()
    assert result.status == "valid"
