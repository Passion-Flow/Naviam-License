"""私钥加密 / 解密 —— 所有 backend 共用。

加密方案：
- KDF: scrypt(passphrase, salt, N=2^14, r=8, p=1, dklen=32)
  - 内存硬 KDF；CPU + 内存双昂贵，挡住 GPU 暴力破解
- AEAD: AES-256-GCM
  - 内置完整性（GCM tag），任何篡改都会解密失败
- 每条记录独立 salt + nonce（不重用）

落盘 / 传输格式（二进制紧凑）：
    magic(4) | version(1) | salt(16) | nonce(12) | ciphertext(N) | tag(16)
    其中 magic = b"FRGK"，version = 1

设计权衡：
- 没用 Fernet —— Fernet 用 HMAC-SHA256 而非 GCM，且要求 base64，落盘大
- 没用 libsodium —— cryptography 已是项目依赖，避免额外引入 libsodium
"""
from __future__ import annotations

import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"FRGK"
VERSION = 1
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class DecryptionFailed(Exception):
    """密文损坏 / 密码错误 / 篡改检测。

    刻意**不**提供详细原因，避免侧信道（让攻击者无法区分密码错与篡改）。
    """


def encrypt(plaintext: bytes, passphrase: str) -> bytes:
    """加密私钥，返回紧凑二进制（含 magic / version / salt / nonce / ciphertext+tag）。"""
    if not passphrase:
        raise ValueError("passphrase must not be empty")

    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(passphrase, salt)

    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, associated_data=MAGIC)

    return MAGIC + bytes([VERSION]) + salt + nonce + ciphertext_and_tag


def decrypt(blob: bytes, passphrase: str) -> bytes:
    """解密私钥。任何错误（magic / version / 解密失败）都抛 DecryptionFailed。"""
    header_len = len(MAGIC) + 1 + SALT_LEN + NONCE_LEN
    if len(blob) < header_len + 16:  # 至少 16 字节 tag
        raise DecryptionFailed("blob too short")

    offset = 0
    if blob[offset : offset + len(MAGIC)] != MAGIC:
        raise DecryptionFailed("bad magic")
    offset += len(MAGIC)

    version = blob[offset]
    offset += 1
    if version != VERSION:
        raise DecryptionFailed(f"unsupported version: {version}")

    salt = blob[offset : offset + SALT_LEN]
    offset += SALT_LEN
    nonce = blob[offset : offset + NONCE_LEN]
    offset += NONCE_LEN
    ciphertext_and_tag = blob[offset:]

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data=MAGIC)
    except InvalidTag as exc:
        raise DecryptionFailed("decryption failed (wrong passphrase or tampered ciphertext)") from exc


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_LEN, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(passphrase.encode("utf-8"))


__all__ = ["DecryptionFailed", "MAGIC", "VERSION", "decrypt", "encrypt"]
