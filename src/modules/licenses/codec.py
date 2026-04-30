"""License 文件与 Activation Code 编解码。

协议：crypto-spec.md §4 / §5。
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any

import cbor2

from modules.activations.cloud_id_codec import (
    _base32_decode,
    _base32_encode,
    _checksum,
    _group,
    _ungroup,
)


def encode_license_payload(
    *,
    schema_version: int = 1,
    license_id: str,
    product_code: str,
    customer_id: str,
    cloud_id_binding: bytes,
    not_before: int,
    not_after: int,
    grace_seconds: int,
    notes: str = "",
    signature_algo: str = "ed25519",
    signature_kid: str = "",
) -> bytes:
    """生成 License 的 canonical CBOR payload（不含签名）。"""
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "license_id": license_id,
        "product_code": product_code,
        "customer_id": customer_id,
        "cloud_id_binding": cloud_id_binding,
        "not_before": not_before,
        "not_after": not_after,
        "grace_seconds": grace_seconds,
        "signature_algo": signature_algo,
        "signature_kid": signature_kid,
    }
    if notes:
        payload["notes"] = notes
    return cbor2.dumps(payload, canonical=True)


def encode_license_file(
    payload_canonical: bytes,
    signature: bytes,
    kid: str,
) -> bytes:
    """生成 License 文件字节（base64url 编码前的 CBOR 包）。"""
    envelope = {
        "v": 1,
        "payload": payload_canonical,
        "sig": signature,
        "kid": kid,
    }
    return cbor2.dumps(envelope, canonical=True)


def encode_activation_code(license_file_bytes: bytes) -> str:
    """生成 Activation Code（人类可读 base32 分组）。"""
    wrapper = {
        "v": 1,
        "license_file": license_file_bytes,
        "checksum": _checksum(license_file_bytes),
    }
    raw = cbor2.dumps(wrapper, canonical=True)
    return _group(_base32_encode(raw))


def decode_license_file(data: bytes) -> dict[str, Any]:
    """解码 License 文件 CBOR 包。不验签。"""
    return cbor2.loads(data)


def decode_activation_code(text: str) -> bytes:
    """解码 Activation Code 得到 license_file 字节。校验 checksum。"""
    text = _ungroup(text)
    raw = _base32_decode(text)
    wrapper = cbor2.loads(raw)
    license_file = wrapper["license_file"]
    expected = wrapper["checksum"]
    actual = _checksum(license_file)
    if not hashlib.sha256(expected).digest() == hashlib.sha256(actual).digest():
        raise ValueError("activation code checksum mismatch")
    return license_file
