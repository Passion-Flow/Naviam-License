"""Ed25519 签名实现。

基于 cryptography 库：
- 密钥对：raw 32 字节私钥 + raw 32 字节公钥
- 签名：64 字节 detached
- 性能高、密钥小，Forge 默认推荐算法
"""
from __future__ import annotations

import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.core.signing.interface import KeyPair, Signature


class Ed25519Signer:
    algorithm = "ed25519"

    def generate_keypair(self) -> KeyPair:
        private_key = Ed25519PrivateKey.generate()
        raw_private = private_key.private_bytes_raw()
        raw_public = private_key.public_key().public_bytes_raw()
        return KeyPair(
            algorithm=self.algorithm,
            key_id=self._new_key_id(),
            public_key=raw_public,
            private_key=raw_private,
        )

    def sign(self, *, private_key: bytes, key_id: str, payload: bytes) -> Signature:
        sk = Ed25519PrivateKey.from_private_bytes(private_key)
        sig = sk.sign(payload)
        return Signature(algorithm=self.algorithm, key_id=key_id, signature=sig)

    def verify(self, *, public_key: bytes, payload: bytes, signature: bytes) -> bool:
        pk = Ed25519PublicKey.from_public_bytes(public_key)
        try:
            pk.verify(signature, payload)
            return True
        except InvalidSignature:
            return False

    def _new_key_id(self) -> str:
        return f"ed25519-{uuid.uuid4().hex[:12]}"
