"""Verifier 类型 / 错误码定义。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

VerificationStatus = Literal[
    "valid",
    "expired",
    "revoked",
    "binding_mismatch",
    "binding_anomaly",    # soft binding 检测到指纹变化，不阻断仅标记
    "signature_invalid",
    "unknown_key",
    "malformed",
    "network_error",
    "grace_period",
]

Mode = Literal["offline", "hybrid", "online"]
Algorithm = Literal["ed25519", "rsa2048", "rsa4096", "sm2"]
Binding = Literal["none", "soft", "hard"]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    status: VerificationStatus
    license_id: str | None
    valid_until: datetime | None
    features: dict[str, object]
    limits: dict[str, object]
    fingerprint: str | None = None       # 当前部署指纹（hybrid/online 上报心跳用）
    reason: str | None = None
