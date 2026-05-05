"""License 文件 codec round-trip 测试（不依赖 Django）。

钉死后端 encode_license_envelope/encode_license_file 与 SDK loader 的兼容性：
SDK loader 的解码顺序 = base64url 解码 → CBOR 解包 → 取 v/payload/sig/kid。
本测试用相同顺序解码后端的产物，证明两端契约一致。
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import cbor2

# 让 src/ 进 path（Django 项目结构，src 是 root package 父）
_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from modules.licenses.codec import (  # noqa: E402
    decode_activation_code,
    decode_license_file,
    encode_activation_code,
    encode_license_envelope,
    encode_license_file,
    encode_license_payload,
)


def _payload_bytes() -> bytes:
    return encode_license_payload(
        license_id="LIC-TEST",
        product_code="default",
        customer_id="00000000-0000-0000-0000-000000000001",
        cloud_id_binding=b"C-XXXX-YYYY",
        not_before=1735689600,  # 2025-01-01
        not_after=1767225600,   # 2026-01-01
        grace_seconds=30 * 24 * 3600,
        notes="round-trip",
        signature_kid="v1-2026-04",
    )


def test_envelope_round_trip() -> None:
    payload = _payload_bytes()
    sig = b"\x01" * 64
    kid = "v1-2026-04"

    env_bytes = encode_license_envelope(payload, sig, kid)
    obj = cbor2.loads(env_bytes)

    assert obj == {"v": 1, "payload": payload, "sig": sig, "kid": kid}


def test_license_file_is_base64url_text_roundtrip() -> None:
    """encode_license_file → decode_license_file 还原同一份 envelope_bytes。"""
    payload = _payload_bytes()
    sig = b"\x02" * 64
    env_bytes = encode_license_envelope(payload, sig, "v1-2026-04")

    license_file_text = encode_license_file(env_bytes)
    # 必须是 ASCII，无 padding
    assert license_file_text.isascii()
    assert "=" not in license_file_text

    # 用 SDK loader 的同款解码逻辑还原
    pad = (-len(license_file_text)) % 4
    decoded = base64.urlsafe_b64decode(license_file_text + ("=" * pad))
    assert decoded == env_bytes

    # codec 自带的 decode_license_file 应当与 SDK loader 同结果
    assert decode_license_file(license_file_text) == env_bytes


def test_sdk_loader_compatible_envelope_dict() -> None:
    """模拟 SDK loader.load_license_file 的最小逻辑路径。"""
    payload = _payload_bytes()
    sig = b"\x03" * 64
    kid = "v1-2026-04"
    env_bytes = encode_license_envelope(payload, sig, kid)
    text = encode_license_file(env_bytes)

    # === 这一段是 SDK loader.load_license_file 的纯函数等价物 ===
    pad = (-len(text)) % 4
    raw = base64.urlsafe_b64decode(text + ("=" * pad))
    envelope = cbor2.loads(raw)
    assert isinstance(envelope, dict)
    assert envelope["v"] == 1
    assert isinstance(envelope["payload"], bytes)
    assert isinstance(envelope["sig"], bytes)
    assert isinstance(envelope["kid"], str)
    # ====================================================

    # 再解 inner payload，确认字段名 / 时间字段类型
    inner = cbor2.loads(envelope["payload"])
    assert inner["product_code"] == "default"
    assert isinstance(inner["not_before"], int)
    assert isinstance(inner["not_after"], int)


def test_activation_code_wraps_same_envelope() -> None:
    """Activation Code 与 license_file 必须 wrap 同一份 envelope_bytes。"""
    payload = _payload_bytes()
    sig = b"\x04" * 64
    env_bytes = encode_license_envelope(payload, sig, "v1-2026-04")

    activation_code = encode_activation_code(env_bytes)
    recovered = decode_activation_code(activation_code)
    assert recovered == env_bytes
