"""RSA 验签（与 forge-server 对偶；独立实现，不共享代码）。

约定：
- PSS padding + SHA-256（与 server 端 PSS_PADDING 一致）
- 公钥 PEM (SubjectPublicKeyInfo)
- 支持 rsa2048 + rsa4096（公钥本身含 key_size 信息）
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


_PSS = padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()),
    salt_length=padding.PSS.MAX_LENGTH,
)
_HASH = hashes.SHA256()


def verify(public_key: bytes, payload: bytes, signature: bytes) -> bool:
    try:
        pk = serialization.load_pem_public_key(public_key)
    except (ValueError, TypeError):
        return False
    if not isinstance(pk, rsa.RSAPublicKey):
        return False
    try:
        pk.verify(signature, payload, _PSS, _HASH)
        return True
    except InvalidSignature:
        return False
