"""argon2id 密码哈希（私有化交付推荐）。

为什么 argon2id（不是 bcrypt）：
- 内存硬（抗 GPU/ASIC 暴力破解）
- argon2id 是 OWASP 2024 password storage cheat sheet 首选
- 默认参数 (t=2, m=65536KB=64MB, p=1) 在现代服务器上 < 100ms

哈希字符串格式自带版本 + 参数，便于将来调高 cost 后无感升级
（needs_rehash → 用户下次登录时静默重哈）。
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerifyMismatchError,
    VerificationError,
)


class PasswordError(Exception):
    """密码相关失败统一基类。"""


# 全局 hasher 单例（其参数可调）
_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=64 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    """生成 argon2id 哈希字符串（含算法 id + 参数 + salt + hash）。"""
    if not plaintext:
        raise PasswordError("password must not be empty")
    return _HASHER.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """验证密码；任何失败（错密码 / 哈希格式损坏）都返回 False。

    刻意不区分错密码 vs 损坏哈希以减少侧信道。
    """
    if not plaintext or not hashed:
        return False
    try:
        return _HASHER.verify(hashed, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """若 hasher 参数已升级，旧哈希需要在下次登录时重哈。"""
    try:
        return _HASHER.check_needs_rehash(hashed)
    except InvalidHashError:
        return True
