"""KeyStorage 统一接口 + 共用数据结构。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

KeyStatus = Literal["active", "rotated", "revoked"]


class KeyStorageError(Exception):
    """密钥存取异常基类。"""


@dataclass(frozen=True, slots=True)
class KeyRecord:
    """密钥的明文表示（仅在内存中持有，不应序列化日志）。"""

    key_id: str
    algorithm: str               # ed25519 / rsa2048 / rsa4096 / sm2
    public_key: bytes            # raw / PEM 视算法
    private_key: bytes           # **明文**——仅在解密后短暂持有
    status: KeyStatus
    created_at: datetime
    activated_at: datetime | None = None
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None


class KeyStorage(Protocol):
    """密钥存储统一接口。

    - 私钥落盘**必须加密**（passphrase 派生 + AEAD）
    - 公钥可明文落盘（便于 Verifier 拉取）
    - metadata 含状态、时间戳、算法
    """

    @property
    def backend_name(self) -> str: ...

    async def save(self, record: KeyRecord) -> None:
        """落盘 / 落对象存储 / 入 KMS。私钥**必须**加密。"""
        ...

    async def load(self, key_id: str) -> KeyRecord:
        """从存储恢复 KeyRecord（含解密后私钥）。"""
        ...

    async def list_ids(self) -> list[str]:
        """列出所有 key_id（不含私钥；不解密）。"""
        ...

    async def load_public(self, key_id: str) -> tuple[bytes, str]:
        """仅取公钥 + 算法（不解密私钥；公钥发布 endpoint 用）。"""
        ...

    async def update_status(self, key_id: str, status: KeyStatus) -> None:
        """更新状态（activate / rotate / revoke）。"""
        ...

    async def delete(self, key_id: str) -> None:
        """删除密钥（极少用；通常 revoke 即可）。"""
        ...
