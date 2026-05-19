"""Object Storage 适配层 — 用到该分类则全部 8 个 provider 必须实现（HARD RULE）。"""
from __future__ import annotations

from app.adapters.object_storage.interface.protocol import ObjectStorage


def get_object_storage() -> ObjectStorage:
    from app.settings import get_settings

    settings = get_settings()
    match settings.object_storage_type:
        case "local":
            from app.adapters.object_storage.local.adapter import LocalObjectStorage
            return LocalObjectStorage.from_settings(settings)
        case "s3":
            from app.adapters.object_storage.s3.adapter import S3ObjectStorage
            return S3ObjectStorage.from_settings(settings)
        case "azure-blob":
            from app.adapters.object_storage.azure_blob.adapter import AzureBlobObjectStorage
            return AzureBlobObjectStorage.from_settings(settings)
        case "aliyun-oss":
            from app.adapters.object_storage.aliyun_oss.adapter import AliyunOssObjectStorage
            return AliyunOssObjectStorage.from_settings(settings)
        case "google-storage":
            from app.adapters.object_storage.google_storage.adapter import GoogleStorageObjectStorage
            return GoogleStorageObjectStorage.from_settings(settings)
        case "tencent-cos":
            from app.adapters.object_storage.tencent_cos.adapter import TencentCosObjectStorage
            return TencentCosObjectStorage.from_settings(settings)
        case "volcengine-tos":
            from app.adapters.object_storage.volcengine_tos.adapter import VolcengineTosObjectStorage
            return VolcengineTosObjectStorage.from_settings(settings)
        case "huawei-obs":
            from app.adapters.object_storage.huawei_obs.adapter import HuaweiObsObjectStorage
            return HuaweiObsObjectStorage.from_settings(settings)
        case _ as t:
            raise ValueError(f"Unsupported object storage type: {t}")


__all__ = ["ObjectStorage", "get_object_storage"]
