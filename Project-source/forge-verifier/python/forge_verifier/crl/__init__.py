"""Verifier 端 CRL —— 解析、验签、检查 license 是否被吊销。

与 forge-server 端 crl 同源不共享代码（项目独立铁律）。
"""
from forge_verifier.crl.fetcher import CrlFetcher, FetchResult
from forge_verifier.crl.parsing import (
    CRL_MAGIC,
    CrlFile,
    CrlFileError,
    CrlMetadata,
    RevocationEntry,
    RevocationListPayload,
    unpack_crl,
)
from forge_verifier.crl.verifier import (
    CrlExpired,
    CrlInvalid,
    CrlVerificationError,
    verify_and_load_crl,
)

__all__ = [
    "CRL_MAGIC",
    "CrlExpired",
    "CrlFetcher",
    "CrlFile",
    "CrlFileError",
    "CrlInvalid",
    "CrlMetadata",
    "CrlVerificationError",
    "FetchResult",
    "RevocationEntry",
    "RevocationListPayload",
    "unpack_crl",
    "verify_and_load_crl",
]
