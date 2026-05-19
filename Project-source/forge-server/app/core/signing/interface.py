"""签名引擎统一接口（所有算法必须实现）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class KeyPair:
    """密钥对。私钥已序列化（具体编码由算法定）。"""

    algorithm: str
    key_id: str            # 内部 ID（uuid 或 hash 前缀）
    public_key: bytes      # 公钥（PEM / raw 视算法）
    private_key: bytes     # 私钥（PEM / raw 视算法）—— 必须立即加密落盘 / 装载内存


@dataclass(frozen=True, slots=True)
class Signature:
    """签名结果。"""

    algorithm: str
    key_id: str
    signature: bytes


class Signer(Protocol):
    """签名引擎统一接口。"""

    @property
    def algorithm(self) -> str:
        """返回 'ed25519' / 'rsa2048' / 'rsa4096' / 'sm2'。"""
        ...

    def generate_keypair(self) -> KeyPair:
        """生成新密钥对。"""
        ...

    def sign(self, *, private_key: bytes, key_id: str, payload: bytes) -> Signature:
        """对 payload 做 detached signature。"""
        ...

    def verify(self, *, public_key: bytes, payload: bytes, signature: bytes) -> bool:
        """验证签名是否有效。"""
        ...
