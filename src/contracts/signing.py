"""Signing abstraction shared by signing and audit modules.

A 方案 = FileKeySigner（age/sops + passphrase）。
KMS / HSM 在第二阶段实现，复用同一 Protocol。
"""
from __future__ import annotations

from typing import Protocol


class IKeySigner(Protocol):
    def kid(self) -> str: ...
    def public_key(self) -> bytes: ...   # 32 字节（Ed25519）
    def sign(self, payload: bytes) -> bytes: ...   # 64 字节
