"""SDK 异常。

所有异常都继承 LicenseSDKError；调用方可以单点捕获。
"""
from __future__ import annotations


class LicenseSDKError(Exception):
    """SDK 顶层异常基类。"""


class InvalidSignature(LicenseSDKError):
    """签名校验失败：签名/payload/公钥不匹配。"""


class Expired(LicenseSDKError):
    """License 已过期且超出 grace。"""


class Revoked(LicenseSDKError):
    """License 已被吊销（在线模式或离线包中显式标记）。"""


class ProductMismatch(LicenseSDKError):
    """License 的 product_code 与 SDK 调用方声明的 product_code 不一致。"""


class SchemaVersionUnsupported(LicenseSDKError):
    """License 的 schema_version 大于本 SDK 支持的最大版本。"""


class CloudIDMismatch(LicenseSDKError):
    """License 中的 cloud_id_binding 与运行环境实际 cloud_id 不一致。"""
