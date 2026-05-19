"""RSA 签名实现（PSS padding + SHA-256）。

加固选择：
- PSS（Probabilistic Signature Scheme）比 PKCS#1 v1.5 更现代、有 PSS salt 抗适应性攻击
- SHA-256 hash
- 密钥编码：PEM PKCS#8（私钥）+ SubjectPublicKeyInfo（公钥）
"""
from __future__ import annotations

import uuid
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.signing.interface import KeyPair, Signature


PSS_PADDING = padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()),
    salt_length=padding.PSS.MAX_LENGTH,
)
HASH_ALGORITHM = hashes.SHA256()


class RsaSigner:
    def __init__(self, *, key_size: Literal[2048, 4096]) -> None:
        if key_size not in (2048, 4096):
            raise ValueError(f"unsupported key_size: {key_size}")
        self._key_size = key_size

    @property
    def algorithm(self) -> str:
        return f"rsa{self._key_size}"

    def generate_keypair(self) -> KeyPair:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=self._key_size)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return KeyPair(
            algorithm=self.algorithm,
            key_id=self._new_key_id(),
            public_key=public_pem,
            private_key=private_pem,
        )

    def sign(self, *, private_key: bytes, key_id: str, payload: bytes) -> Signature:
        sk = serialization.load_pem_private_key(private_key, password=None)
        if not isinstance(sk, rsa.RSAPrivateKey):
            raise ValueError("provided private_key is not an RSA private key")
        sig = sk.sign(payload, PSS_PADDING, HASH_ALGORITHM)
        return Signature(algorithm=self.algorithm, key_id=key_id, signature=sig)

    def verify(self, *, public_key: bytes, payload: bytes, signature: bytes) -> bool:
        pk = serialization.load_pem_public_key(public_key)
        if not isinstance(pk, rsa.RSAPublicKey):
            return False
        try:
            pk.verify(signature, payload, PSS_PADDING, HASH_ALGORITHM)
            return True
        except InvalidSignature:
            return False

    def _new_key_id(self) -> str:
        return f"rsa{self._key_size}-{uuid.uuid4().hex[:12]}"
