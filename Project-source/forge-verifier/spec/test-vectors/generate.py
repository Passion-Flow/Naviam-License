"""跨语言互操作测试向量生成器。

用法：
    cd Forge/Project-source/forge-verifier/spec/test-vectors
    python generate.py

每个测试目录：
    NNN-<algo>-<mode>-<binding>/
    ├── keypair.json        # 测试用密钥对（base64 raw）— 绝不在生产复用
    ├── payload.json        # 待签的 payload（规范化后的字节流）
    ├── expected.forge      # 用密钥对签发并打包的 .forge 文件（hex 编码到 expected.forge.hex 便于看 diff）
    └── expected-verify.json# 用该 keypair.public + expected.forge 验签后的期望结果

Python / TS / Go 各实现必须能跑通本目录的所有向量。
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    from gmssl import sm2 as _sm2  # type: ignore
except Exception:  # noqa: BLE001
    _sm2 = None


HERE = Path(__file__).resolve().parent

# Deterministic SM2 keypair (ASCII-hex). Generated once via gmssl; pinned so the
# vector bytes are reproducible across re-runs. NEVER use in production.
SM2_PRIVATE_HEX = "3945208f7b2144b13f36e38ac6d39f95889393692860b51a42fb81ef4df7c5b8"
SM2_PUBLIC_HEX = (
    "09f9df311e5421a150dd7d161e4bc5c672179fad1833fc076bb08ff356f35020"
    "ccea490ce26775a52dc6ea718cc1aa600aed05fbf35e084a6632f6072da9ad13"
)


@dataclass
class Vector:
    name: str
    algorithm: str
    mode: str
    binding: str
    bound_fingerprint: str | None = None
    expires_in_days: int = 365


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _add_tar_entry(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def generate_vector(v: Vector) -> None:
    out_dir = HERE / v.name
    out_dir.mkdir(parents=True, exist_ok=True)

    # 固定 issued_at 让向量可复现（不用 datetime.now）
    issued = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    expires = issued + timedelta(days=v.expires_in_days)

    payload = {
        "protocol_version": "1.0",
        "license_id": f"vector-{v.name}",
        "customer_id": "cust-test",
        "product_id": "prod-test",
        "mode": v.mode,
        "scope": "customer_x_product",
        "binding": v.binding,
        "bound_fingerprint": v.bound_fingerprint,
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
        "features": {"sso": True},
        "limits": {"max_users": 10},
    }
    payload_bytes = _canonical(payload)

    if v.algorithm == "ed25519":
        sk = Ed25519PrivateKey.generate()
        raw_private = sk.private_bytes_raw()
        raw_public = sk.public_key().public_bytes_raw()
        signature = sk.sign(payload_bytes)
        public_b64 = base64.b64encode(raw_public).decode()
        private_b64 = base64.b64encode(raw_private).decode()
    elif v.algorithm == "sm2":
        if _sm2 is None:
            raise RuntimeError("gmssl not available; `pip install gmssl` first")
        # ASCII-hex wire format — pubkey / signature live in .forge as hex bytes
        # (see spec/forge-file-layout.md). Matches all language SDK impls.
        signer = _sm2.CryptSM2(private_key=SM2_PRIVATE_HEX, public_key=SM2_PUBLIC_HEX)
        sig_hex = signer.sign_with_sm3(payload_bytes)
        signature = sig_hex.encode("ascii")  # bytes written to signature.bin
        # For interop, store the ASCII-hex pubkey *bytes* (verifiers load these
        # as-is and decode hex themselves).
        public_b64 = base64.b64encode(SM2_PUBLIC_HEX.encode("ascii")).decode()
        private_b64 = base64.b64encode(SM2_PRIVATE_HEX.encode("ascii")).decode()
    else:
        raise NotImplementedError(f"algorithm not yet supported in generator: {v.algorithm}")

    metadata = {
        "magic": "forg",
        "forge_version": "1.0",
        "algorithm": v.algorithm,
        "key_id": f"{v.algorithm}-vector",
        "signed_at": issued.isoformat(),
    }
    metadata_bytes = _canonical(metadata)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_tar_entry(tar, "payload.json", payload_bytes)
        _add_tar_entry(tar, "signature.bin", signature)
        _add_tar_entry(tar, "metadata.json", metadata_bytes)
    forge_bytes = buf.getvalue()

    (out_dir / "keypair.json").write_text(
        json.dumps(
            {
                "algorithm": v.algorithm,
                "private_key_b64": private_b64,
                "public_key_b64": public_b64,
                "key_id": f"{v.algorithm}-vector",
            },
            indent=2,
            sort_keys=True,
        )
    )
    (out_dir / "payload.json").write_bytes(payload_bytes)
    (out_dir / "expected.forge").write_bytes(forge_bytes)
    (out_dir / "expected.forge.hex").write_text(binascii.hexlify(forge_bytes).decode() + "\n")
    (out_dir / "expected-verify.json").write_text(
        json.dumps(
            {
                "status": "valid",
                "license_id": payload["license_id"],
                "expires_at": payload["expires_at"],
                "binding": payload["binding"],
                "fingerprint_must_match": payload["bound_fingerprint"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"  ✓ {v.name}/")


def main() -> int:
    print("Generating Forge interop test vectors…")
    vectors = [
        Vector(name="001-ed25519-offline-none", algorithm="ed25519", mode="offline", binding="none"),
        Vector(name="002-ed25519-hybrid-soft",  algorithm="ed25519", mode="hybrid",  binding="soft"),
        Vector(
            name="003-ed25519-offline-hard",
            algorithm="ed25519",
            mode="offline",
            binding="hard",
            # 用一个稳定的 SHA-256 摘要当 fingerprint（仅向量需要）
            bound_fingerprint="a" * 64,
        ),
        Vector(name="004-sm2-offline-none", algorithm="sm2", mode="offline", binding="none"),
    ]
    for v in vectors:
        generate_vector(v)
    print("Done. Vectors written to:", HERE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
