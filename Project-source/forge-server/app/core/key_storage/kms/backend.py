"""KMS backend —— 占位。

私钥**永远不离开 KMS**：sign() 操作走 KMS 的远程签名 API，本地只暂存公钥。
这与 local_file / object_storage 的"私钥加密落地、本地解密签"模型不同，需要：
- 改造 Signer 接口让"签名"成为可异步远程调用
- 各 KMS（Vault Transit / AWS KMS / 阿里 KMS / 华为 DEW / 火山 KMS）写独立 SubProvider

待整体 RSA / SM2 完工 + 心跳 / CRL 端到端跑通后再启动。
"""
from __future__ import annotations

from app.core.key_storage.interface import KeyRecord, KeyStatus, KeyStorage
from app.settings import Settings


class KmsKeyStorage(KeyStorage):
    backend_name = "kms"

    @classmethod
    def from_settings(cls, settings: Settings) -> "KmsKeyStorage":
        return cls()

    async def save(self, record: KeyRecord) -> None:
        raise NotImplementedError("KMS backend pending — see app/core/key_storage/kms/backend.py header")

    async def load(self, key_id: str) -> KeyRecord:
        raise NotImplementedError("KMS backend pending")

    async def list_ids(self) -> list[str]:
        raise NotImplementedError("KMS backend pending")

    async def load_public(self, key_id: str) -> tuple[bytes, str]:
        raise NotImplementedError("KMS backend pending")

    async def update_status(self, key_id: str, status: KeyStatus) -> None:
        raise NotImplementedError("KMS backend pending")

    async def delete(self, key_id: str) -> None:
        raise NotImplementedError("KMS backend pending")
