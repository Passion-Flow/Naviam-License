"""Cloud ID v1 编解码。

编码：CBOR -> SHA-256 前 4 字节 checksum -> base32 -> 每 6 字符加 '-'。
解码：逆序；校验 checksum、字段、时间偏差。
"""
from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import cbor2


class CloudIDError(ValueError):
    """Cloud ID 解码或校验失败。"""


# 字段名常量（canonical CBOR map key order）
_CLOUD_ID_FIELDS = [
    "schema_version",
    "product_code",
    "instance_id",
    "instance_pubkey_fp",
    "hardware_fp",
    "nonce",
    "created_at",
]


def _checksum(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()[:4]


def _base32_encode(data: bytes) -> str:
    # 标准 base32 大写，去掉尾部 '='
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _base32_decode(text: str) -> bytes:
    # 补回 padding
    pad = 8 - (len(text) % 8)
    if pad != 8:
        text += "=" * pad
    return base64.b32decode(text, casefold=True)


def _group(text: str, size: int = 6) -> str:
    return "-".join(text[i : i + size] for i in range(0, len(text), size))


def _ungroup(text: str) -> str:
    return text.replace("-", "").replace(" ", "").upper()


def encode(cloud_id_map: dict[str, Any]) -> str:
    """将 Cloud ID 字典编码为人类可读字符串。"""
    canonical = cbor2.dumps(cloud_id_map, canonical=True)
    cs = _checksum(canonical)
    b32 = _base32_encode(canonical + cs)
    return _group(b32)


def decode(text: str, *, max_age_seconds: int = 600, now: datetime | None = None) -> dict[str, Any]:
    """解码并校验 Cloud ID。

    失败时抛 CloudIDError。
    """
    text = _ungroup(text)
    if len(text) < 8:
        raise CloudIDError("too short")

    try:
        raw = _base32_decode(text)
    except Exception as exc:
        raise CloudIDError(f"base32 decode failed: {exc}") from exc

    if len(raw) < 5:
        raise CloudIDError("decoded too short")

    payload = raw[:-4]
    expected_cs = raw[-4:]
    actual_cs = _checksum(payload)
    if not _constant_time_compare(expected_cs, actual_cs):
        raise CloudIDError("checksum mismatch")

    try:
        obj = cbor2.loads(payload)
    except Exception as exc:
        raise CloudIDError(f"cbor decode failed: {exc}") from exc

    if not isinstance(obj, dict):
        raise CloudIDError("root is not a map")

    _validate_fields(obj)
    _validate_timestamps(obj, max_age_seconds=max_age_seconds, now=now)
    return obj


def _validate_fields(obj: dict[str, Any]) -> None:
    if int(obj.get("schema_version", 0)) != 1:
        raise CloudIDError("unsupported schema_version")
    if len(obj.get("instance_pubkey_fp", b"")) != 16:
        raise CloudIDError("instance_pubkey_fp must be 16 bytes")
    if len(obj.get("hardware_fp", b"")) != 32:
        raise CloudIDError("hardware_fp must be 32 bytes")
    if len(obj.get("nonce", b"")) != 16:
        raise CloudIDError("nonce must be 16 bytes")


def _validate_timestamps(
    obj: dict[str, Any],
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    created_at = int(obj.get("created_at", 0))
    server_ts = int(now.timestamp())
    if abs(server_ts - created_at) > max_age_seconds:
        raise CloudIDError("created_at too far from server time")


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return False
    return hashlib.sha256(a).digest() == hashlib.sha256(b).digest()
