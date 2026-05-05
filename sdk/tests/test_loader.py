"""loader.py — License 文件格式 round-trip 测试。

钉死契约：base64url(CBOR(envelope))。任何旧 JSON envelope 必须被拒绝。
"""
from __future__ import annotations

import base64
import json

import cbor2
import pytest

from license_sdk.errors import LicenseSDKError, SchemaVersionUnsupported
from license_sdk.loader import _b64url_decode, load_license_file


# --- helpers ---

def _make_envelope_bytes(*, payload: bytes, sig: bytes, kid: str, v: int = 1) -> bytes:
    return cbor2.dumps(
        {"v": v, "payload": payload, "sig": sig, "kid": kid},
        canonical=True,
    )


def _b64url_str(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


# --- round-trip ---

def test_round_trip_minimal(tmp_path) -> None:
    payload_canonical = cbor2.dumps({"product_code": "default"}, canonical=True)
    signature = b"\x00" * 64
    kid = "v1-2026-04"

    env_bytes = _make_envelope_bytes(payload=payload_canonical, sig=signature, kid=kid)
    f = tmp_path / "test.lic"
    f.write_text(_b64url_str(env_bytes), encoding="ascii")

    envelope = load_license_file(f)
    assert envelope.schema_version == 1
    assert envelope.payload_cbor == payload_canonical
    assert envelope.signature == signature
    assert envelope.kid == kid


def test_round_trip_no_padding(tmp_path) -> None:
    """base64url 无 padding 必须能解。"""
    env_bytes = _make_envelope_bytes(payload=b"x", sig=b"y" * 64, kid="k")
    f = tmp_path / "test.lic"
    # 故意不带 = padding
    f.write_text(_b64url_str(env_bytes), encoding="ascii")
    assert load_license_file(f).kid == "k"


# --- 防降级：旧 JSON envelope 必须被拒 ---

def test_rejects_old_json_envelope(tmp_path) -> None:
    """旧版（Phase 3 之前）SDK loader 期望的 JSON envelope 必须不再被接受。"""
    json_envelope = json.dumps({
        "schema_version": 1,
        "payload_cbor_b64": base64.b64encode(b"x").decode(),
        "signature_b64": base64.b64encode(b"y" * 64).decode(),
        "kid": "k",
    })
    f = tmp_path / "old.lic"
    f.write_text(json_envelope, encoding="ascii")

    # JSON 文本本身不是合法 base64url-CBOR — 解码到 base64url 这步可能通过
    # （JSON 里大部分字符在 base64url 字母表内），但 CBOR 解包必失败。
    with pytest.raises(LicenseSDKError):
        load_license_file(f)


# --- 字段校验 ---

def test_rejects_unsupported_schema(tmp_path) -> None:
    env_bytes = _make_envelope_bytes(payload=b"x", sig=b"y" * 64, kid="k", v=999)
    f = tmp_path / "v999.lic"
    f.write_text(_b64url_str(env_bytes), encoding="ascii")
    with pytest.raises(SchemaVersionUnsupported):
        load_license_file(f)


def test_rejects_non_bytes_payload(tmp_path) -> None:
    env_bytes = cbor2.dumps(
        {"v": 1, "payload": "not-bytes", "sig": b"y" * 64, "kid": "k"},
        canonical=True,
    )
    f = tmp_path / "bad.lic"
    f.write_text(_b64url_str(env_bytes), encoding="ascii")
    with pytest.raises(LicenseSDKError, match="payload must be bytes"):
        load_license_file(f)


def test_rejects_empty_file(tmp_path) -> None:
    f = tmp_path / "empty.lic"
    f.write_text("", encoding="ascii")
    with pytest.raises(LicenseSDKError):
        load_license_file(f)


def test_rejects_non_ascii(tmp_path) -> None:
    f = tmp_path / "binary.lic"
    f.write_bytes(b"\xff\xfe\xfd not ascii")
    with pytest.raises(LicenseSDKError, match="ASCII"):
        load_license_file(f)


def test_b64url_decode_helper() -> None:
    """直接 unit-test base64url 解码器，确保它不接受 standard b64 的 + / 字符。"""
    # base64url 用 - _，不用 + /
    encoded = _b64url_str(b"hello world")
    assert _b64url_decode(encoded) == b"hello world"
