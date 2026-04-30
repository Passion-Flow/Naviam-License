"""FileKeySigner 实现（A 方案）。

启动时从文件加载 Ed25519 私钥；私钥只留在进程内存。
若部署层使用 age/sops 加密，则由 init 脚本解密到 tmpfs 后本模块读取明文。
"""
from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from contracts.signing import IKeySigner


class FileKeySigner:
    """从文件加载的 Ed25519 签名器。

    支持格式：
    - PEM（PKCS#8 或 OpenSSH）
    - 原始 32 字节私钥
    """

    def __init__(self, key_path: str, kid: str) -> None:
        self._kid = kid
        raw = Path(key_path).read_bytes()
        if b"PRIVATE KEY" in raw or b"OPENSSH" in raw:
            self._sk = serialization.load_pem_private_key(raw, password=None)
            if not isinstance(self._sk, Ed25519PrivateKey):
                raise ValueError("private key is not Ed25519")
        elif len(raw) == 32:
            self._sk = Ed25519PrivateKey.from_private_bytes(raw)
        elif len(raw) == 64:
            # Some formats include public key appended; take first 32 bytes
            self._sk = Ed25519PrivateKey.from_private_bytes(raw[:32])
        else:
            raise ValueError(
                f"unsupported key format: length={len(raw)}; expected PEM or 32/64 raw bytes"
            )
        self._pk = self._sk.public_key()

    def kid(self) -> str:
        return self._kid

    def public_key(self) -> bytes:
        return self._pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def sign(self, payload: bytes) -> bytes:
        return self._sk.sign(payload)


def get_signer() -> IKeySigner:
    from django.conf import settings

    return FileKeySigner(
        key_path=settings.SIGNING_KEY_PATH,
        kid=settings.SIGNING_KEY_KID,
    )


def get_audit_signer() -> IKeySigner:
    from django.conf import settings

    return FileKeySigner(
        key_path=settings.AUDIT_KEY_PATH,
        kid=settings.AUDIT_KEY_KID,
    )
