"""License 文件与 Activation Code 编解码。

协议：crypto-spec.md §4 / §5。

格式约定（V1，不变）：
- envelope_bytes = canonical CBOR({v: 1, payload: payload_canonical, sig: signature, kid: kid})
- license_file   = base64url(envelope_bytes) 的 ASCII 文本（无 padding "="）
- activation_code = group6( base32( CBOR({v: 1, license_file: envelope_bytes, checksum: SHA-256(envelope_bytes)[:4]}) ) )

License 文件 = "可写到磁盘 / 跨主机传输"的标准产物；SDK loader 直接消费这一文本。
Activation Code = "人类可输入"的离线短码；wrap 同一份 envelope_bytes。两条路径在签名层等价。
"""
from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass
from typing import Any

import cbor2

from modules.activations.cloud_id_codec import (
    _base32_decode,
    _base32_encode,
    _checksum,
    _group,
    _ungroup,
)


@dataclass(frozen=True)
class LicenseArtifacts:
    """一次签发产生的两种交付形态。两者等价，仅传输/输入习惯不同。"""

    license_file: str       # base64url(CBOR(envelope))，落盘为 *.lic
    activation_code: str    # base32 分组人类可读串，离线手动输入


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


def encode_license_envelope(
    payload_canonical: bytes,
    signature: bytes,
    kid: str,
) -> bytes:
    """canonical CBOR({v, payload, sig, kid}) — license_file 与 activation_code 的共同源。"""
    envelope = {
        "v": 1,
        "payload": payload_canonical,
        "sig": signature,
        "kid": kid,
    }
    return cbor2.dumps(envelope, canonical=True)


def encode_license_file(envelope_bytes: bytes) -> str:
    """落盘格式：base64url(envelope_bytes)，无 padding。返回 ASCII 字符串。

    生成的字符串可以直接 `*.lic` 写盘；SDK loader 反向解码。
    """
    return base64.urlsafe_b64encode(envelope_bytes).rstrip(b"=").decode("ascii")


def decode_license_file(text: str) -> bytes:
    """反向：把磁盘上的 *.lic 文本还原为 envelope_bytes。

    不验签 — 验签由 SDK 持公钥侧完成。这里仅做格式解码。
    """
    s = text.strip()
    pad = (-len(s)) % 4
    return base64.urlsafe_b64decode(s + ("=" * pad))


def encode_activation_code(envelope_bytes: bytes) -> str:
    """生成 Activation Code（人类可读 base32 分组）。wrap 同一份 envelope_bytes。"""
    wrapper = {
        "v": 1,
        "license_file": envelope_bytes,
        "checksum": _checksum(envelope_bytes),
    }
    raw = cbor2.dumps(wrapper, canonical=True)
    return _group(_base32_encode(raw))


def decode_activation_code(text: str) -> bytes:
    """解码 Activation Code 还原 envelope_bytes；checksum 用 hmac.compare_digest 防侧信道。"""
    text = _ungroup(text)
    raw = _base32_decode(text)
    wrapper = cbor2.loads(raw)
    envelope_bytes = wrapper["license_file"]
    expected = wrapper["checksum"]
    actual = _checksum(envelope_bytes)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("activation code checksum mismatch")
    return envelope_bytes


def decode_license_envelope(envelope_bytes: bytes) -> dict[str, Any]:
    """CBOR 解包 envelope；不验签。"""
    obj = cbor2.loads(envelope_bytes)
    if not isinstance(obj, dict):
        raise ValueError("license envelope root is not a CBOR map")
    return obj
