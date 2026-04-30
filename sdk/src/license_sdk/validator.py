"""License 校验逻辑（纯函数）。

输入：已经反序列化的 license_payload + 期望的 product_id + 当前时间。
输出：(status, reason)。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .errors import (
    CloudIDMismatch,
    Expired,
    ProductMismatch,
    Revoked,
)

# 状态字符串约定
STATUS_ACTIVE = "active"
STATUS_GRACE = "grace"
STATUS_EXPIRED = "expired"
STATUS_REVOKED = "revoked"
STATUS_INVALID = "invalid"


@dataclass(frozen=True)
class ValidationResult:
    status: str
    reason: str


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


def validate_payload(
    payload: Mapping[str, Any],
    *,
    expected_product_id: str,
    expected_cloud_id: str | None,
    now: datetime | None = None,
    grace_seconds: int = 30 * 24 * 3600,
) -> ValidationResult:
    """对解码后的 license_payload 做语义校验。

    - product_id 不匹配 -> 抛 ProductMismatch（硬错）。
    - cloud_id_binding 与运行环境不匹配 -> 抛 CloudIDMismatch。
    - 已被 revoked（payload['revoked']=True）-> 抛 Revoked。
    - not_before / not_after / grace 由本函数计算，返回 ValidationResult。
    """
    now = now or datetime.now(timezone.utc)

    product_id = str(payload.get("product_id"))
    if product_id != expected_product_id:
        raise ProductMismatch(
            f"license product_id={product_id!r} != expected={expected_product_id!r}"
        )

    cloud_id_binding = payload.get("cloud_id_binding")
    if expected_cloud_id is not None and cloud_id_binding != expected_cloud_id:
        raise CloudIDMismatch(
            f"license cloud_id_binding != runtime cloud_id"
        )

    if bool(payload.get("revoked", False)):
        raise Revoked(str(payload.get("revoked_reason") or "revoked"))

    not_before = _parse_iso(str(payload["not_before"]))
    not_after = _parse_iso(str(payload["not_after"]))

    if now < not_before:
        return ValidationResult(STATUS_INVALID, "license not yet valid (not_before)")
    if now <= not_after:
        return ValidationResult(STATUS_ACTIVE, "ok")

    grace_until = not_after.timestamp() + grace_seconds
    if now.timestamp() <= grace_until:
        return ValidationResult(STATUS_GRACE, "in grace window")

    raise Expired("license expired beyond grace")
