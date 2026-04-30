"""从磁盘加载 License 与 公钥。

License 文件格式：
- offline 包是一个 JSON 文件，结构：
  {
    "schema_version": 1,
    "payload_cbor_b64": "...",  // base64 of canonical CBOR(license_payload)
    "signature_b64": "...",     // base64 of Ed25519 signature
    "kid": "..."
  }

不做格式协商；版本不匹配 -> SchemaVersionUnsupported。
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from .errors import LicenseSDKError, SchemaVersionUnsupported

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


@dataclass(frozen=True)
class LicenseEnvelope:
    schema_version: int
    payload_cbor: bytes
    signature: bytes
    kid: str


def load_license_file(path: str | Path) -> LicenseEnvelope:
    raw = Path(path).read_bytes()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseSDKError("license file is not valid JSON") from exc

    schema_version = obj.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionUnsupported(f"unsupported schema_version={schema_version!r}")

    try:
        payload = base64.b64decode(obj["payload_cbor_b64"], validate=True)
        signature = base64.b64decode(obj["signature_b64"], validate=True)
        kid = str(obj["kid"])
    except (KeyError, ValueError) as exc:
        raise LicenseSDKError("license envelope missing/invalid fields") from exc

    return LicenseEnvelope(
        schema_version=int(schema_version),
        payload_cbor=payload,
        signature=signature,
        kid=kid,
    )


def load_public_key_file(path: str | Path) -> bytes:
    return Path(path).read_bytes()
