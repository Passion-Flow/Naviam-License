"""Azure Blob Storage 适配器（azure-storage-blob 同步 + asyncio.to_thread 包装）。

Azure 术语对齐：
- bucket ↔ container
- key    ↔ blob name

鉴权：account_url（如 https://<account>.blob.core.windows.net）+ account_key。
account_name 从 endpoint host 段截取，用于 SAS 签名。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class AzureBlobObjectStorage(ObjectStorage):
    provider_name = "azure-blob"

    def __init__(
        self,
        *,
        account_url: str = "",
        account_name: str = "",
        account_key: str = "",
    ) -> None:
        self._account_url = account_url
        self._account_name = account_name
        self._account_key = account_key
        self._service_client: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "AzureBlobObjectStorage":
        url = settings.object_storage_endpoint
        host = urlparse(url).hostname or ""
        account = host.split(".")[0] if host else ""
        return cls(
            account_url=url,
            account_name=account,
            account_key=settings.object_storage_access_key_secret,
        )

    @classmethod
    def from_client(cls, client: Any) -> "AzureBlobObjectStorage":
        """测试钩子：注入 BlobServiceClient-like 对象。"""
        instance = cls()
        instance._service_client = client
        return instance

    async def connect(self) -> None:
        if self._service_client is not None:
            return
        from azure.storage.blob import BlobServiceClient  # type: ignore
        self._service_client = await asyncio.to_thread(
            BlobServiceClient,
            account_url=self._account_url,
            credential=self._account_key or None,
        )

    async def disconnect(self) -> None:
        if self._service_client is not None:
            try:
                await asyncio.to_thread(self._service_client.close)
            except Exception:
                pass
        self._service_client = None

    async def health_check(self) -> bool:
        if self._service_client is None:
            return False
        try:
            await asyncio.to_thread(self._service_client.get_service_properties)
            return True
        except Exception:
            return False

    def _ensure(self) -> Any:
        if self._service_client is None:
            raise RuntimeError("Azure Blob not connected; call connect() first")
        return self._service_client

    def _blob(self, container: str, blob: str) -> Any:
        return self._ensure().get_blob_client(container=container, blob=blob)

    def _container(self, container: str) -> Any:
        return self._ensure().get_container_client(container)

    async def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> ObjectMetadata:
        def _upload() -> Any:
            return self._blob(bucket, key).upload_blob(
                data,
                overwrite=True,
                content_settings=_ContentSettings(content_type=content_type),
                metadata=metadata or None,
            )
        result = await asyncio.to_thread(_upload)
        etag = ""
        if isinstance(result, dict):
            etag = result.get("etag", "")
        else:
            etag = getattr(result, "etag", "") or ""
        return ObjectMetadata(
            bucket=bucket, key=key, size=len(data),
            etag=etag.strip('"'),
            content_type=content_type, last_modified=datetime.now(timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        def _download() -> bytes:
            return self._blob(bucket, key).download_blob().readall()
        return await asyncio.to_thread(_download)

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._blob(bucket, key).delete_blob)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            return bool(await asyncio.to_thread(self._blob(bucket, key).exists))
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        props = await asyncio.to_thread(self._blob(bucket, key).get_blob_properties)
        size = int(getattr(props, "size", 0) or 0)
        etag = (getattr(props, "etag", "") or "").strip('"')
        cs = getattr(props, "content_settings", None)
        content_type = getattr(cs, "content_type", "application/octet-stream") if cs else "application/octet-stream"
        last_modified = getattr(props, "last_modified", datetime.now(timezone.utc))
        return ObjectMetadata(
            bucket=bucket, key=key, size=size, etag=etag,
            content_type=content_type, last_modified=last_modified,
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        def _collect() -> list[Any]:
            return list(self._container(bucket).list_blobs(name_starts_with=prefix or None))
        for it in await asyncio.to_thread(_collect):
            yield ObjectMetadata(
                bucket=bucket,
                key=getattr(it, "name", ""),
                size=int(getattr(it, "size", 0) or 0),
                etag=(getattr(it, "etag", "") or "").strip('"'),
                content_type="application/octet-stream",
                last_modified=getattr(it, "last_modified", datetime.now(timezone.utc)),
            )

    async def ensure_bucket(self, bucket: str) -> None:
        try:
            await asyncio.to_thread(self._ensure().create_container, name=bucket)
        except Exception:
            pass

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        from azure.storage.blob import (  # type: ignore
            BlobSasPermissions,
            generate_blob_sas,
        )
        expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        sas = await asyncio.to_thread(
            generate_blob_sas,
            account_name=self._account_name,
            container_name=bucket,
            blob_name=key,
            account_key=self._account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        return f"{self._account_url.rstrip('/')}/{bucket}/{key}?{sas}"

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        from azure.storage.blob import (  # type: ignore
            BlobSasPermissions,
            generate_blob_sas,
        )
        expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        sas = await asyncio.to_thread(
            generate_blob_sas,
            account_name=self._account_name,
            container_name=bucket,
            blob_name=key,
            account_key=self._account_key,
            permission=BlobSasPermissions(write=True, create=True),
            expiry=expiry,
        )
        return f"{self._account_url.rstrip('/')}/{bucket}/{key}?{sas}"


class _ContentSettings:
    """轻量替身：azure-storage-blob 未装时仍能 import 本模块。
    Azure SDK 在真上传时只读 content_type 属性。"""

    def __init__(self, *, content_type: str) -> None:
        self.content_type = content_type
