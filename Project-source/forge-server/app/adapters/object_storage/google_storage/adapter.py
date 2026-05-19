"""Google Cloud Storage 适配器（google-cloud-storage 同步 + asyncio.to_thread 包装）。

鉴权：service account JSON（base64 / 路径），通过 `object_storage_access_key_secret`
传入；若为空走 Application Default Credentials（GCP 内置 metadata server）。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class GoogleStorageObjectStorage(ObjectStorage):
    provider_name = "google-storage"

    def __init__(self, *, credentials_json: str = "", project_id: str = "") -> None:
        self._credentials_json = credentials_json
        self._project_id = project_id
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "GoogleStorageObjectStorage":
        return cls(
            credentials_json=settings.object_storage_access_key_secret,
            # project_id 复用 region 字段（设计选择：避免 settings 字段爆炸）
            project_id=settings.object_storage_region,
        )

    @classmethod
    def from_client(cls, client: Any) -> "GoogleStorageObjectStorage":
        """测试钩子：注入 Client-like 对象（含 .bucket(name) → Bucket）。"""
        instance = cls()
        instance._client = client
        return instance

    async def connect(self) -> None:
        if self._client is not None:
            return
        from google.cloud import storage  # type: ignore
        if self._credentials_json:
            from google.oauth2 import service_account  # type: ignore
            info = json.loads(self._credentials_json)
            credentials = service_account.Credentials.from_service_account_info(info)
            self._client = await asyncio.to_thread(
                storage.Client,
                project=self._project_id or info.get("project_id"),
                credentials=credentials,
            )
        else:
            self._client = await asyncio.to_thread(storage.Client, project=self._project_id or None)

    async def disconnect(self) -> None:
        self._client = None

    async def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            # 仅触发一次廉价 API
            await asyncio.to_thread(lambda: list(self._client.list_buckets(max_results=1)))
            return True
        except Exception:
            return False

    def _ensure(self) -> Any:
        if self._client is None:
            raise RuntimeError("GCS not connected; call connect() first")
        return self._client

    def _blob(self, bucket: str, key: str) -> Any:
        return self._ensure().bucket(bucket).blob(key)

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
            blob = self._blob(bucket, key)
            if metadata:
                blob.metadata = metadata
            blob.upload_from_string(data, content_type=content_type)
            return blob
        blob = await asyncio.to_thread(_upload)
        return ObjectMetadata(
            bucket=bucket, key=key, size=len(data),
            etag=(getattr(blob, "etag", "") or "").strip('"'),
            content_type=content_type, last_modified=datetime.now(timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        def _download() -> bytes:
            return self._blob(bucket, key).download_as_bytes()
        return await asyncio.to_thread(_download)

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._blob(bucket, key).delete)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            return bool(await asyncio.to_thread(self._blob(bucket, key).exists))
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        def _reload() -> Any:
            blob = self._blob(bucket, key)
            blob.reload()
            return blob
        blob = await asyncio.to_thread(_reload)
        return ObjectMetadata(
            bucket=bucket, key=key,
            size=int(getattr(blob, "size", 0) or 0),
            etag=(getattr(blob, "etag", "") or "").strip('"'),
            content_type=getattr(blob, "content_type", "application/octet-stream") or "application/octet-stream",
            last_modified=getattr(blob, "updated", datetime.now(timezone.utc)),
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        def _collect() -> list[Any]:
            return list(self._ensure().list_blobs(bucket, prefix=prefix or None))
        for it in await asyncio.to_thread(_collect):
            yield ObjectMetadata(
                bucket=bucket,
                key=getattr(it, "name", ""),
                size=int(getattr(it, "size", 0) or 0),
                etag=(getattr(it, "etag", "") or "").strip('"'),
                content_type=getattr(it, "content_type", "application/octet-stream") or "application/octet-stream",
                last_modified=getattr(it, "updated", datetime.now(timezone.utc)),
            )

    async def ensure_bucket(self, bucket: str) -> None:
        try:
            await asyncio.to_thread(self._ensure().get_bucket, bucket)
        except Exception:
            await asyncio.to_thread(self._ensure().create_bucket, bucket)

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        def _sign() -> str:
            return self._blob(bucket, key).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=ttl_seconds),
                method="GET",
            )
        return await asyncio.to_thread(_sign)

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        def _sign() -> str:
            return self._blob(bucket, key).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=ttl_seconds),
                method="PUT",
            )
        return await asyncio.to_thread(_sign)
