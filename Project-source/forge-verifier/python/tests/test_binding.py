"""三档 binding 端到端测试：none / soft / hard。

每个测试构造一份 .forge 文件 + 控制 Verifier 看到的指纹（fingerprint_override），
验证：
- none：指纹任意都通过
- hard：指纹必须等于 payload.bound_fingerprint
- soft：首次记录，后续指纹改变 → binding_anomaly（不阻断）
       状态文件被篡改 → 当作首次重新记录（HMAC 防篡改）
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


def _build_payload_bytes(
    *,
    license_id: str = "lic-test",
    binding: str = "none",
    bound_fingerprint: str | None = None,
    expires_at: datetime | None = None,
) -> bytes:
    now = datetime.now(timezone.utc)
    payload = {
        "protocol_version": "1.0",
        "license_id": license_id,
        "customer_id": "cust-001",
        "product_id": "prod",
        "mode": "offline",
        "scope": "instance",
        "binding": binding,
        "bound_fingerprint": bound_fingerprint,
        "issued_at": now.isoformat(),
        "expires_at": (expires_at or now + timedelta(days=30)).isoformat(),
        "features": {},
        "limits": {},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _build_forge_tar(payload_bytes: bytes, signature: bytes, metadata: dict) -> bytes:
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


def _sign_and_build(payload_bytes: bytes) -> tuple[bytes, bytes]:
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key().public_bytes_raw()
    sig = sk.sign(payload_bytes)
    metadata = {
        "magic": "forg",
        "forge_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "ed25519-test",
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }
    return _build_forge_tar(payload_bytes, sig, metadata), pk


def _write_license(tmp_path: Path, payload_bytes: bytes) -> tuple[Path, bytes]:
    forge_bytes, pk = _sign_and_build(payload_bytes)
    license_path = tmp_path / "license.forge"
    license_path.write_bytes(forge_bytes)
    return license_path, pk


# ────────────────────────────────────────────────────────────
# binding = none
# ────────────────────────────────────────────────────────────

def test_none_binding_accepts_any_fingerprint(tmp_path: Path) -> None:
    license_path, pk = _write_license(tmp_path, _build_payload_bytes(binding="none"))
    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="any-fingerprint",
    )
    result = verifier.verify_blocking()
    assert result.status == "valid"
    # 指纹经 SHA-256 归一化后是 64 hex 字符
    assert result.fingerprint is not None and len(result.fingerprint) == 64


def test_none_binding_records_fingerprint_for_heartbeat(tmp_path: Path) -> None:
    """none binding 不阻断，但仍采集指纹用于心跳上报。"""
    license_path, pk = _write_license(tmp_path, _build_payload_bytes(binding="none"))
    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="my-deployment-1",
    )
    result = verifier.verify_blocking()
    assert result.status == "valid"
    # fingerprint 不是直接等于 override 字符串，因为 collect_fingerprint 会 SHA-256
    assert result.fingerprint is not None and len(result.fingerprint) == 64


# ────────────────────────────────────────────────────────────
# binding = hard
# ────────────────────────────────────────────────────────────

def test_hard_binding_passes_when_fingerprint_matches(tmp_path: Path) -> None:
    """先采集指纹，再签发 license 把它绑进去，然后用同一指纹启动 → pass。"""
    import hashlib
    fp_value = "my-machine-1"
    expected_fp = hashlib.sha256(f"override={fp_value}".encode()).hexdigest()

    license_path, pk = _write_license(
        tmp_path,
        _build_payload_bytes(binding="hard", bound_fingerprint=expected_fp),
    )
    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override=fp_value,
    )
    result = verifier.verify_blocking()
    assert result.status == "valid"
    assert result.fingerprint == expected_fp


def test_hard_binding_rejects_when_fingerprint_mismatch(tmp_path: Path) -> None:
    """同一份 license 拷到不同 fingerprint 的机器 → binding_mismatch。"""
    import hashlib
    expected_fp = hashlib.sha256(b"override=machine-A").hexdigest()

    license_path, pk = _write_license(
        tmp_path,
        _build_payload_bytes(binding="hard", bound_fingerprint=expected_fp),
    )
    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="machine-B",   # 不同机器
    )
    with pytest.raises(VerificationFailed) as exc_info:
        verifier.verify_blocking()
    assert exc_info.value.status == "binding_mismatch"


def test_hard_binding_rejects_when_no_bound_fingerprint(tmp_path: Path) -> None:
    """hard binding 但 payload 没有 bound_fingerprint → malformed-ish 拒绝。"""
    license_path, pk = _write_license(
        tmp_path,
        _build_payload_bytes(binding="hard", bound_fingerprint=None),
    )
    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="any",
    )
    with pytest.raises(VerificationFailed) as exc_info:
        verifier.verify_blocking()
    assert exc_info.value.status == "binding_mismatch"


# ────────────────────────────────────────────────────────────
# binding = soft
# ────────────────────────────────────────────────────────────

def test_soft_binding_records_on_first_run(tmp_path: Path) -> None:
    license_path, pk = _write_license(tmp_path, _build_payload_bytes(binding="soft"))
    state_dir = tmp_path / "state"
    verifier = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=state_dir,
        fingerprint_override="machine-A",
    )
    result = verifier.verify_blocking()
    assert result.status == "valid"
    # 状态文件应该被创建（限制 600 权限）
    state_files = list(state_dir.glob("*.binding"))
    assert len(state_files) == 1


def test_soft_binding_passes_when_fingerprint_stable(tmp_path: Path) -> None:
    """同一份 license 连续两次启动，指纹不变 → 都 valid。"""
    license_path, pk = _write_license(tmp_path, _build_payload_bytes(binding="soft"))
    state_dir = tmp_path / "state"
    common_kwargs = dict(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=state_dir,
        fingerprint_override="machine-A",
    )
    Verifier(**common_kwargs).verify_blocking()  # 首次记录
    result = Verifier(**common_kwargs).verify_blocking()
    assert result.status == "valid"


def test_soft_binding_anomaly_when_fingerprint_changes(tmp_path: Path) -> None:
    """首次绑 machine-A，第二次启动指纹变成 machine-B → binding_anomaly 不阻断。"""
    license_path, pk = _write_license(tmp_path, _build_payload_bytes(binding="soft"))
    state_dir = tmp_path / "state"
    Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=state_dir,
        fingerprint_override="machine-A",
    ).verify_blocking()

    result = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=state_dir,
        fingerprint_override="machine-B",
    ).verify_blocking()
    assert result.status == "binding_anomaly"
    assert result.reason is not None and "anomaly" in result.reason


def test_soft_binding_detects_tampered_state_file(tmp_path: Path) -> None:
    """状态文件被手改 → HMAC 不匹配 → 视为首次重新记录。

    这意味着攻击者擦除状态文件 / 改 fingerprint 字段，verifier 不会"信任"该篡改，
    会重新采集当前指纹记录。
    """
    license_path, pk = _write_license(tmp_path, _build_payload_bytes(binding="soft"))
    state_dir = tmp_path / "state"

    # 首次：machine-A 被记录
    Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=state_dir,
        fingerprint_override="machine-A",
    ).verify_blocking()

    state_file = next(state_dir.glob("*.binding"))
    original = state_file.read_bytes()
    obj = json.loads(original.decode("utf-8"))
    # 攻击者尝试把 fingerprint 改成 machine-B（与下次启动想要的指纹一致）
    obj["body"]["fingerprint"] = "tampered-value"
    state_file.write_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())

    # 第二次：machine-B 启动；状态文件 HMAC 不匹配 → 当作首次重新记录 → valid
    result = Verifier(
        license_file_path=license_path,
        public_key=pk,
        mode="offline",
        state_dir=state_dir,
        fingerprint_override="machine-B",
    ).verify_blocking()
    assert result.status == "valid"
    assert result.reason and "first-run" in result.reason
