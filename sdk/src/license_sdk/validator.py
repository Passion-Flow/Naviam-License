"""License 校验逻辑（纯函数）。

输入：已经反序列化的 license_payload + 期望的 product_code + 当前 Cloud ID + 时间。
输出：(status, reason)。

字段命名约定（与 docs/security/crypto-spec.md §4 + 后端 codec.py 对齐）：
- payload 内字段：product_code、cloud_id_binding（32 字节 fingerprint）、
                  not_before、not_after、grace_seconds
- not_before / not_after：unix-seconds（int），不是 ISO 字符串
- cloud_id_binding：32 字节 SHA-256，**不是 Cloud ID 文本**；
  fingerprint 由 cloud_id 的"机器特征字段"算出，每次启动重新算应当一致
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .cloud_id import assert_binding_matches
from .errors import (
    CloudIDMismatch,
    Expired,
    LicenseSDKError,
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


def _to_unix_seconds(value: Any, *, field: str) -> int:
    """规范化 not_before / not_after：必须是 int 或可无损转 int 的 float。

    spec/crypto-spec.md §4 规定 not_before / not_after 为 u64 unix-seconds。
    任何非数字（包括 ISO 字符串）都视为契约违反。
    """
    if isinstance(value, bool):  # bool 是 int 的子类，单独排除
        raise LicenseSDKError(f"{field} must be unix-seconds int, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise LicenseSDKError(
        f"{field} must be unix-seconds int (per crypto-spec §4), got {type(value).__name__}"
    )


def validate_payload(
    payload: Mapping[str, Any],
    *,
    expected_product_code: str,
    expected_cloud_id: str | None,
    now: datetime | None = None,
    grace_seconds: int = 30 * 24 * 3600,
) -> ValidationResult:
    """对解码后的 license_payload 做语义校验。

    - product_code 不匹配 -> 抛 ProductMismatch（硬错）。
    - cloud_id_binding 与运行环境不匹配 -> 抛 CloudIDMismatch。
    - 已被 revoked（payload['revoked']=True）-> 抛 Revoked。
    - not_before / not_after / grace 由本函数计算，返回 ValidationResult。
    """
    now = now or datetime.now(timezone.utc)

    product_code = str(payload.get("product_code"))
    if product_code != expected_product_code:
        raise ProductMismatch(
            f"license product_code={product_code!r} != expected={expected_product_code!r}"
        )

    if expected_cloud_id is not None:
        # expected_cloud_id 是运行期 Cloud ID 文本（或已解码 dict — 测试方便）；
        # 内部抽 _BINDING_FIELDS subset → SHA-256 → 32 字节，再用 hmac.compare_digest
        # 与 payload['cloud_id_binding'] 比。失配抛 CloudIDMismatch。
        assert_binding_matches(
            payload.get("cloud_id_binding"),
            expected_cloud_id,
        )

    if bool(payload.get("revoked", False)):
        raise Revoked(str(payload.get("revoked_reason") or "revoked"))

    not_before_ts = _to_unix_seconds(payload["not_before"], field="not_before")
    not_after_ts = _to_unix_seconds(payload["not_after"], field="not_after")
    now_ts = int(now.timestamp())

    if now_ts < not_before_ts:
        return ValidationResult(STATUS_INVALID, "license not yet valid (not_before)")
    if now_ts <= not_after_ts:
        return ValidationResult(STATUS_ACTIVE, "ok")
    if now_ts <= not_after_ts + grace_seconds:
        return ValidationResult(STATUS_GRACE, "in grace window")

    raise Expired("license expired beyond grace")
