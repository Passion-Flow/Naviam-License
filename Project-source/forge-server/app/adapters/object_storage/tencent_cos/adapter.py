"""Tencent COS 适配器（cos-python-sdk-v5 同步 + asyncio.to_thread 包装）。

SDK 用法（同步）：
    from qcloud_cos import CosConfig, CosS3Client
    config = CosConfig(Region=region, SecretId=..., SecretKey=...)
    client = CosS3Client(config)
    client.put_object(Bucket=..., Key=..., Body=data)

COS bucket 名按腾讯规范是 `<name>-<appid>`；本适配器透传 bucket 字符串。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class TencentCosObjectStorage(ObjectStorage):
    provider_name = "tencent-cos"

    def __init__(
        self,
        *,
        region: str = "",
        secret_id: str = "",
        secret_key: str = "",
    ) -> None:
        self._region = region
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "TencentCosObjectStorage":
        return cls(
            region=settings.object_storage_region,
            secret_id=settings.object_storage_access_key_id,
            secret_key=settings.object_storage_access_key_secret,
        )

    @classmethod
    def from_client(cls, client: Any) -> "TencentCosObjectStorage":
        """测试钩子：注入 CosS3Client-like 对象。"""
        instance = cls()
        instance._client = client
        return instance

    async def connect(self) -> None:
        if self._client is not None:
            return
        from qcloud_cos import CosConfig, CosS3Client  # type: ignore
        config = CosConfig(
            Region=self._region,
            SecretId=self._secret_id,
            SecretKey=self._secret_key,
        )
        self._client = await asyncio.to_thread(CosS3Client, config)

    async def disconnect(self) -> None:
        self._client = None

    async def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            await asyncio.to_thread(self._client.list_buckets)
            return True
        except Exception:
            return False

    def _ensure(self) -> Any:
        if self._client is None:
            raise RuntimeError("Tencent COS not connected; call connect() first")
        return self._client

    async def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> ObjectMetadata:
        kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if metadata:
            kwargs["Metadata"] = metadata
        response = await asyncio.to_thread(self._ensure().put_object, **kwargs)
        etag = (response.get("ETag") if isinstance(response, dict) else "") or ""
        return ObjectMetadata(
            bucket=bucket, key=key, size=len(data),
            etag=etag.strip('"'),
            content_type=content_type, last_modified=datetime.now(timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        response = await asyncio.to_thread(self._ensure().get_object, Bucket=bucket, Key=key)
        body = response["Body"] if isinstance(response, dict) else getattr(response, "Body", None)
        # cos sdk 返回 StreamBody，有 get_raw_stream / get_stream / read
        for method in ("get_raw_stream", "get_stream"):
            stream = getattr(body, method, None)
            if callable(stream):
                stream_obj = await asyncio.to_thread(stream)
                return await asyncio.to_thread(stream_obj.read)
        if hasattr(body, "read"):
            return await asyncio.to_thread(body.read)
        return bytes(body or b"")

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._ensure().delete_object, Bucket=bucket, Key=key)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            return bool(await asyncio.to_thread(self._ensure().object_exists, Bucket=bucket, Key=key))
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        response = await asyncio.to_thread(self._ensure().head_object, Bucket=bucket, Key=key)
        d = response if isinstance(response, dict) else {}
        return ObjectMetadata(
            bucket=bucket, key=key,
            size=int(d.get("Content-Length") or d.get("ContentLength") or 0),
            etag=(d.get("ETag") or "").strip('"'),
            content_type=d.get("Content-Type") or d.get("ContentType") or "application/octet-stream",
            last_modified=datetime.now(timezone.utc),
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix
        response = await asyncio.to_thread(self._ensure().list_objects, **kwargs)
        contents = (response or {}).get("Contents", []) if isinstance(response, dict) else []
        for obj in contents:
            yield ObjectMetadata(
                bucket=bucket,
                key=obj.get("Key", ""),
                size=int(obj.get("Size", 0) or 0),
                etag=(obj.get("ETag") or "").strip('"'),
                content_type="application/octet-stream",
                last_modified=datetime.now(timezone.utc),
            )

    async def ensure_bucket(self, bucket: str) -> None:
        client = self._ensure()
        try:
            await asyncio.to_thread(client.head_bucket, Bucket=bucket)
        except Exception:
            await asyncio.to_thread(client.create_bucket, Bucket=bucket)

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        url = await asyncio.to_thread(
            self._ensure().get_presigned_url,
            Method="GET",
            Bucket=bucket,
            Key=key,
            Expired=ttl_seconds,
        )
        return str(url)

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        url = await asyncio.to_thread(
            self._ensure().get_presigned_url,
            Method="PUT",
            Bucket=bucket,
            Key=key,
            Expired=ttl_seconds,
        )
        return str(url)
