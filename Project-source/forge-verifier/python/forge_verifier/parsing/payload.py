"""License payload 解析（Verifier 侧独立实现 — 与 forge-server 同源不共享）。

规范化字节流的算法必须与 forge-server 一致：
- sort_keys=True
- separators=(",", ":")
- ensure_ascii=False
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class LicensePayload:
    protocol_version: str
    license_id: str
    customer_id: str
    product_id: str
    mode: str            # offline | hybrid | online
    scope: str           # customer_x_product | customer_bundle | instance
    binding: str         # none | soft | hard
    bound_fingerprint: str | None
    issued_at: datetime
    expires_at: datetime
    features: dict[str, Any]
    limits: dict[str, Any]

    @classmethod
    def from_canonical_bytes(cls, raw: bytes) -> "LicensePayload":
        obj = json.loads(raw.decode("utf-8"))
        return cls(
            protocol_version=obj["protocol_version"],
            license_id=obj["license_id"],
            customer_id=obj["customer_id"],
            product_id=obj["product_id"],
            mode=obj["mode"],
            scope=obj["scope"],
            binding=obj["binding"],
            bound_fingerprint=obj.get("bound_fingerprint"),
            issued_at=datetime.fromisoformat(obj["issued_at"]),
            expires_at=datetime.fromisoformat(obj["expires_at"]),
            features=obj.get("features", {}),
            limits=obj.get("limits", {}),
        )
