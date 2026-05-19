"""签名密钥的安全存储 — 私钥不可明文落盘。

3 个 backend（local_file / object_storage / kms），统一接口；通过
`settings.key_storage_backend` 选择激活。

业务代码只看 KeyStorage Protocol，不接触底层文件 / 网络。
"""
from __future__ import annotations

from app.core.key_storage.interface import KeyRecord, KeyStorage, KeyStorageError


def get_key_storage() -> KeyStorage:
    from app.settings import get_settings

    settings = get_settings()
    backend = settings.key_storage_backend

    if backend == "local_file":
        from app.core.key_storage.local_file.backend import LocalFileKeyStorage
        return LocalFileKeyStorage.from_settings(settings)
    if backend == "object_storage":
        from app.core.key_storage.object_storage.backend import ObjectStorageKeyStorage
        return ObjectStorageKeyStorage.from_settings(settings)
    if backend == "kms":
        from app.core.key_storage.kms.backend import KmsKeyStorage
        return KmsKeyStorage.from_settings(settings)
    raise ValueError(f"Unsupported key_storage_backend: {backend!r}")


__all__ = ["KeyRecord", "KeyStorage", "KeyStorageError", "get_key_storage"]
