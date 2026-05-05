"""validator.py 单元测试。

字段约定（与 docs/security/crypto-spec.md §4 + 后端 codec.py 对齐）：
- product_code（不是 product_id）
- not_before / not_after：u64 unix-seconds（int），不是 ISO 字符串
- cloud_id_binding：32 字节 SHA-256 fingerprint（不是 Cloud ID 文本）

凭证不可复制的核心机制就在 fingerprint 上：
不同机器 hardware_fp 不同 → fingerprint 不同 → CloudIDMismatch。
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

import cbor2
import pytest

from license_sdk.cloud_id import binding_fingerprint
from license_sdk.errors import (
    CloudIDMismatch,
    Expired,
    LicenseSDKError,
    ProductMismatch,
    Revoked,
)
from license_sdk.validator import (
    STATUS_ACTIVE,
    STATUS_GRACE,
    validate_payload,
)


# --- helpers ---


def _ts(*args: int) -> int:
    return int(datetime(*args, tzinfo=timezone.utc).timestamp())


def _cloud_id_dict(**overrides) -> dict:
    base: dict = {
        "schema_version": 1,
        "product_code": "default",
        "instance_id": b"INST-A",
        "instance_pubkey_fp": b"\x10" * 16,
        "hardware_fp": b"\x20" * 32,
        "nonce": b"\x30" * 16,
        "created_at": _ts(2026, 6, 1),
    }
    base.update(overrides)
    return base


def _encode_cloud_id(d: dict) -> str:
    """构造合法的 Cloud ID 文本，用于把 dict → 用户面 API 期望的字符串。"""
    canonical = cbor2.dumps(d, canonical=True)
    cs = hashlib.sha256(canonical).digest()[:4]
    b32 = base64.b32encode(canonical + cs).decode("ascii").rstrip("=")
    return "-".join(b32[i : i + 6] for i in range(0, len(b32), 6))


def _payload(**overrides) -> dict:
    base: dict = {
        "product_code": "default",
        "cloud_id_binding": binding_fingerprint(_cloud_id_dict()),  # 32 bytes
        "not_before": _ts(2026, 1, 1),
        "not_after": _ts(2027, 1, 1),
    }
    base.update(overrides)
    return base


def _valid_cloud_id_text() -> str:
    return _encode_cloud_id(_cloud_id_dict())


# --- 时间窗 ---


def test_active_within_window() -> None:
    result = validate_payload(
        _payload(),
        expected_product_code="default",
        expected_cloud_id=_valid_cloud_id_text(),
        now=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert result.status == STATUS_ACTIVE


def test_grace_after_expiry() -> None:
    result = validate_payload(
        _payload(),
        expected_product_code="default",
        expected_cloud_id=_valid_cloud_id_text(),
        now=datetime(2027, 1, 15, tzinfo=timezone.utc),
    )
    assert result.status == STATUS_GRACE


def test_expired_beyond_grace() -> None:
    with pytest.raises(Expired):
        validate_payload(
            _payload(),
            expected_product_code="default",
            expected_cloud_id=_valid_cloud_id_text(),
            now=datetime(2027, 3, 1, tzinfo=timezone.utc),
            grace_seconds=30 * 24 * 3600,
        )


# --- 字段不匹配 ---


def test_product_mismatch() -> None:
    with pytest.raises(ProductMismatch):
        validate_payload(
            _payload(product_code="other"),
            expected_product_code="default",
            expected_cloud_id=_valid_cloud_id_text(),
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


def test_revoked() -> None:
    with pytest.raises(Revoked):
        validate_payload(
            _payload(revoked=True, revoked_reason="manual"),
            expected_product_code="default",
            expected_cloud_id=_valid_cloud_id_text(),
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


# --- Cloud ID 绑定 (Phase 4 核心) ---


def test_cloud_id_binding_skip_when_none() -> None:
    """expected_cloud_id=None 时跳过 fingerprint 校验（在线模式由心跳兜底）。"""
    result = validate_payload(
        _payload(),
        expected_product_code="default",
        expected_cloud_id=None,
        now=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert result.status == STATUS_ACTIVE


def test_cloud_id_binding_matches_with_different_nonce() -> None:
    """同一台机器：Cloud ID 重新生成（nonce/created_at 变）必须仍能通过 fingerprint。"""
    same_machine_new_nonce = _cloud_id_dict(
        nonce=b"\xff" * 16,
        created_at=_ts(2026, 12, 1),
    )
    result = validate_payload(
        _payload(),
        expected_product_code="default",
        expected_cloud_id=_encode_cloud_id(same_machine_new_nonce),
        now=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert result.status == STATUS_ACTIVE


def test_cloud_id_binding_rejects_different_hardware() -> None:
    """关键测试：把 License 复制到另一台机器（hardware_fp 不同）必须失败。"""
    other_machine = _cloud_id_dict(hardware_fp=b"\xaa" * 32)
    with pytest.raises(CloudIDMismatch):
        validate_payload(
            _payload(),
            expected_product_code="default",
            expected_cloud_id=_encode_cloud_id(other_machine),
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


def test_cloud_id_binding_rejects_different_instance_pubkey() -> None:
    """复制到另一台 SDK 实例（instance_pubkey_fp 不同）也必须失败。"""
    other_instance = _cloud_id_dict(instance_pubkey_fp=b"\xbb" * 16)
    with pytest.raises(CloudIDMismatch):
        validate_payload(
            _payload(),
            expected_product_code="default",
            expected_cloud_id=_encode_cloud_id(other_instance),
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


def test_cloud_id_binding_rejects_non_bytes_in_payload() -> None:
    """payload 内的 cloud_id_binding 必须是 bytes；旧版字符串形式应被拒绝。"""
    with pytest.raises(CloudIDMismatch):
        validate_payload(
            _payload(cloud_id_binding="C-XXXX-YYYY"),  # 旧契约：字符串
            expected_product_code="default",
            expected_cloud_id=_valid_cloud_id_text(),
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


def test_cloud_id_binding_rejects_wrong_length() -> None:
    """payload 内 fingerprint 必须正好 32 字节。"""
    with pytest.raises(CloudIDMismatch):
        validate_payload(
            _payload(cloud_id_binding=b"\x00" * 16),
            expected_product_code="default",
            expected_cloud_id=_valid_cloud_id_text(),
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


# --- 时间格式回归 ---


def test_iso_string_now_rejected() -> None:
    """旧契约（ISO 字符串）必须被明确拒绝。"""
    with pytest.raises(LicenseSDKError):
        validate_payload(
            _payload(not_before="2026-01-01T00:00:00Z"),
            expected_product_code="default",
            expected_cloud_id=_valid_cloud_id_text(),
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
