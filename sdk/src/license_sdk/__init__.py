"""License 校验 SDK（Python）。

公开接口：

    from license_sdk import LicenseClient, LicenseStatus, OnlineConfig
    from license_sdk.errors import (
        LicenseSDKError,
        InvalidSignature,
        Expired,
        Revoked,
        ProductMismatch,
    )
"""
from __future__ import annotations

from .client import LicenseClient, LicenseStatus, OnlineConfig
from .errors import (
    Expired,
    InvalidSignature,
    LicenseSDKError,
    ProductMismatch,
    Revoked,
)

__all__ = [
    "LicenseClient",
    "LicenseStatus",
    "OnlineConfig",
    "LicenseSDKError",
    "InvalidSignature",
    "Expired",
    "Revoked",
    "ProductMismatch",
]

__version__ = "0.1.0"
