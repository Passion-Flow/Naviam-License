"""validator.py 单元测试占位。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from license_sdk.errors import Expired, ProductMismatch, Revoked
from license_sdk.validator import (
    STATUS_ACTIVE,
    STATUS_GRACE,
    validate_payload,
)


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "product_id": "default",
        "cloud_id_binding": "C-XXXX",
        "not_before": "2026-01-01T00:00:00Z",
        "not_after": "2027-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_active_within_window() -> None:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    result = validate_payload(
        _payload(),
        expected_product_id="default",
        expected_cloud_id="C-XXXX",
        now=now,
    )
    assert result.status == STATUS_ACTIVE


def test_grace_after_expiry() -> None:
    now = datetime(2027, 1, 15, tzinfo=timezone.utc)
    result = validate_payload(
        _payload(),
        expected_product_id="default",
        expected_cloud_id="C-XXXX",
        now=now,
    )
    assert result.status == STATUS_GRACE


def test_expired_beyond_grace() -> None:
    now = datetime(2027, 3, 1, tzinfo=timezone.utc)
    with pytest.raises(Expired):
        validate_payload(
            _payload(),
            expected_product_id="default",
            expected_cloud_id="C-XXXX",
            now=now,
            grace_seconds=30 * 24 * 3600,
        )


def test_product_mismatch() -> None:
    with pytest.raises(ProductMismatch):
        validate_payload(
            _payload(product_id="other"),
            expected_product_id="default",
            expected_cloud_id="C-XXXX",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


def test_revoked() -> None:
    with pytest.raises(Revoked):
        validate_payload(
            _payload(revoked=True, revoked_reason="manual revoke"),
            expected_product_id="default",
            expected_cloud_id="C-XXXX",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
