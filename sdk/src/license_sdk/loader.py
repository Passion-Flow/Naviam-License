"""从磁盘加载 License 与公钥。

License 文件格式（与 docs/security/crypto-spec.md §4 + 后端 codec.py 对齐）：

    *.lic 文件 = base64url( CBOR( {
        v: 1,
        payload: payload_canonical_bytes,
        sig: signature_64_bytes,
        kid: kid_str,
    } ) )

文件内容是 ASCII 文本（无 padding "="），可跨平台传输；不做编码协商。
任何不符合本格式的文件 → SchemaVersionUnsupported / LicenseSDKError。
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cbor2

from .errors import LicenseSDKError, SchemaVersionUnsupported

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


@dataclass(frozen=True)
class LicenseEnvelope:
    schema_version: int  # = envelope["v"]
    payload_cbor: bytes
    signature: bytes
    kid: str


def _b64url_decode(text: str) -> bytes:
    """base64url 解码（容忍无 padding）。任何错误 → LicenseSDKError。"""
    s = text.strip()
    if not s:
        raise LicenseSDKError("license file is empty")
    pad = (-len(s)) % 4
    try:
        return base64.urlsafe_b64decode(s + ("=" * pad))
    except (ValueError, TypeError) as exc:
        raise LicenseSDKError("license file is not valid base64url") from exc


def load_license_file(path: str | Path) -> LicenseEnvelope:
    """读取 *.lic 文件，解码 envelope，但不验签。

    解析顺序：
      1. 文件 → ASCII 文本
      2. base64url 解码 → CBOR envelope_bytes
      3. CBOR 解包 → dict({v, payload, sig, kid})
      4. 字段校验：v ∈ SUPPORTED；payload/sig 是 bytes；kid 是 str
    """
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise LicenseSDKError("license file is not ASCII text") from exc

    envelope_bytes = _b64url_decode(text)

    try:
        envelope: Any = cbor2.loads(envelope_bytes)
    except cbor2.CBORDecodeError as exc:
        raise LicenseSDKError("license envelope is not valid CBOR") from exc

    if not isinstance(envelope, dict):
        raise LicenseSDKError("license envelope root is not a CBOR map")

    schema_version = envelope.get("v")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionUnsupported(f"unsupported envelope v={schema_version!r}")

    payload = envelope.get("payload")
    signature = envelope.get("sig")
    kid = envelope.get("kid")

    if not isinstance(payload, bytes):
        raise LicenseSDKError("envelope.payload must be bytes")
    if not isinstance(signature, bytes):
        raise LicenseSDKError("envelope.sig must be bytes")
    if not isinstance(kid, str):
        raise LicenseSDKError("envelope.kid must be str")

    return LicenseEnvelope(
        schema_version=int(schema_version),
        payload_cbor=payload,
        signature=signature,
        kid=kid,
    )


def load_public_key_file(path: str | Path) -> bytes:
    return Path(path).read_bytes()
