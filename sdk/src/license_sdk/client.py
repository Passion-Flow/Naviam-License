"""SDK 主入口：LicenseClient。

最小可用骨架；真实实现在 V1 阶段补全。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cbor2

from .crypto import load_public_key_pem, verify_signature
from .errors import LicenseSDKError
from .loader import LicenseEnvelope, load_license_file, load_public_key_file
from .online import OnlineConfig
from .validator import (
    STATUS_ACTIVE,
    STATUS_GRACE,
    STATUS_INVALID,
    ValidationResult,
    validate_payload,
)


@dataclass(frozen=True)
class LicenseStatus:
    status: str
    reason: str
    not_after: datetime | None
    grace_until: datetime | None

    def is_active(self) -> bool:
        return self.status in {STATUS_ACTIVE, STATUS_GRACE}


class LicenseClient:
    """License 校验客户端。

    使用：
        client = LicenseClient.from_file(license_path=..., pubkey_path=..., product_code=...)
        status = client.verify()
    """

    def __init__(
        self,
        envelope: LicenseEnvelope,
        public_key_pem: bytes,
        product_code: str,
        cloud_id: str | None = None,
        grace_seconds: int = 30 * 24 * 3600,
        online: OnlineConfig | None = None,
    ) -> None:
        self._envelope = envelope
        self._public_key = load_public_key_pem(public_key_pem)
        self._product_code = product_code
        self._cloud_id = cloud_id
        self._grace_seconds = grace_seconds
        self._online = online  # 心跳实现 V1 阶段补全

    @classmethod
    def from_file(
        cls,
        *,
        license_path: str | Path,
        pubkey_path: str | Path,
        product_code: str,
        cloud_id: str | None = None,
        grace_seconds: int = 30 * 24 * 3600,
        online: OnlineConfig | None = None,
    ) -> "LicenseClient":
        envelope = load_license_file(license_path)
        public_key_pem = load_public_key_file(pubkey_path)
        return cls(
            envelope=envelope,
            public_key_pem=public_key_pem,
            product_code=product_code,
            cloud_id=cloud_id,
            grace_seconds=grace_seconds,
            online=online,
        )

    def verify(self, now: datetime | None = None) -> LicenseStatus:
        """完整校验：签名 -> 反序列化 -> 语义校验。

        失败语义统一通过 LicenseSDKError 子类抛出。成功返回 LicenseStatus。
        """
        # 1. 签名校验：先验后用，绝不在未验签前信任 payload。
        verify_signature(
            self._public_key,
            self._envelope.payload_cbor,
            self._envelope.signature,
        )

        # 2. 反序列化 CBOR。
        try:
            payload: dict[str, Any] = cbor2.loads(self._envelope.payload_cbor)
        except cbor2.CBORDecodeError as exc:
            raise LicenseSDKError("license payload is not valid CBOR") from exc
        if not isinstance(payload, dict):
            raise LicenseSDKError("license payload root is not a map")

        # 3. 语义校验。
        result: ValidationResult = validate_payload(
            payload,
            expected_product_code=self._product_code,
            expected_cloud_id=self._cloud_id,
            now=now,
            grace_seconds=self._grace_seconds,
        )

        not_after_dt = _unix_to_datetime(payload.get("not_after"))
        grace_until_dt = (
            datetime.fromtimestamp(
                not_after_dt.timestamp() + self._grace_seconds, tz=timezone.utc
            )
            if not_after_dt is not None
            else None
        )

        return LicenseStatus(
            status=result.status if result.status != STATUS_INVALID else STATUS_INVALID,
            reason=result.reason,
            not_after=not_after_dt,
            grace_until=grace_until_dt,
        )


def _unix_to_datetime(ts: object) -> datetime | None:
    """payload['not_after'] 是 unix-seconds（int / 整数 float）；其他形态返回 None。"""
    if isinstance(ts, bool):
        return None
    if isinstance(ts, int):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, float) and ts.is_integer():
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return None
