"""签名 / 公钥校验。

只做：加载 PEM/raw 公钥，调用 cryptography 的 Ed25519 verify。
不做：自实现密码学算法、密钥生成、私钥操作。
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature as _CryptoInvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .errors import InvalidSignature


def load_public_key_pem(pem_bytes: bytes) -> Ed25519PublicKey:
    """从 PEM 字节加载 Ed25519 公钥。"""
    key = serialization.load_pem_public_key(pem_bytes)
    if not isinstance(key, Ed25519PublicKey):
        raise InvalidSignature("public key is not Ed25519")
    return key


def verify_signature(public_key: Ed25519PublicKey, payload: bytes, signature: bytes) -> None:
    """校验签名；失败抛 InvalidSignature。"""
    try:
        public_key.verify(signature, payload)
    except _CryptoInvalidSignature as exc:
        raise InvalidSignature("ed25519 verify failed") from exc
