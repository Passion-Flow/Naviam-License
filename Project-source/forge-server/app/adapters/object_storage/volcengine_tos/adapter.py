"""Volcengine TOS 适配器（tos 同步 + asyncio.to_thread 包装）。

火山引擎 TOS Python SDK：
    import tos
    client = tos.TosClientV2(ak, sk, endpoint, region)
    client.put_object(bucket, key, content=data)
    client.get_object(bucket, key).read()
    client.pre_signed_url(tos.HttpMethodType.HttpMethodGet, bucket, key, expires=...)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class VolcengineTosObjectStorage(ObjectStorage):
    provider_name = "volcengine-tos"

    def __init__(
        self,
        *,
        endpoint: str = "",
        region: str = "",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "VolcengineTosObjectStorage":
        return cls(
            endpoint=settings.object_storage_endpoint,
            region=settings.object_storage_region,
            access_key=settings.object_storage_access_key_id,
            secret_key=settings.object_storage_access_key_secret,
        )

    @classmethod
    def from_client(cls, client: Any) -> "VolcengineTosObjectStorage":
        instance = cls()
        instance._client = client
        return instance

    async def connect(self) -> None:
        if self._client is not None:
            return
        import tos  # type: ignore
        self._client = await asyncio.to_thread(
            tos.TosClientV2,
            self._access_key,
            self._secret_key,
            self._endpoint,
            self._region,
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                try:
                    await asyncio.to_thread(close)
                except Exception:
                    pass
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
            raise RuntimeError("Volcengine TOS not connected; call connect() first")
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
        kwargs: dict[str, Any] = {"content": data, "content_type": content_type}
        if metadata:
            kwargs["meta"] = metadata
        result = await asyncio.to_thread(self._ensure().put_object, bucket, key, **kwargs)
        etag = (getattr(result, "etag", "") or "").strip('"')
        return ObjectMetadata(
            bucket=bucket, key=key, size=len(data), etag=etag,
            content_type=content_type, last_modified=datetime.now(timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        out = await asyncio.to_thread(self._ensure().get_object, bucket, key)
        # tos.GetObjectOutput 暴露 .read()
        if hasattr(out, "read"):
            return await asyncio.to_thread(out.read)
        body = getattr(out, "content", None)
        if body is None:
            body = b""
        return bytes(body)

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._ensure().delete_object, bucket, key)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            await asyncio.to_thread(self._ensure().head_object, bucket, key)
            return True
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        meta = await asyncio.to_thread(self._ensure().head_object, bucket, key)
        return ObjectMetadata(
            bucket=bucket, key=key,
            size=int(getattr(meta, "content_length", 0) or 0),
            etag=(getattr(meta, "etag", "") or "").strip('"'),
            content_type=getattr(meta, "content_type", "application/octet-stream") or "application/octet-stream",
            last_modified=getattr(meta, "last_modified", datetime.now(timezone.utc)) or datetime.now(timezone.utc),
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        result = await asyncio.to_thread(self._ensure().list_objects, bucket, prefix=prefix or None)
        contents = getattr(result, "contents", None) or []
        for obj in contents:
            yield ObjectMetadata(
                bucket=bucket,
                key=getattr(obj, "key", ""),
                size=int(getattr(obj, "size", 0) or 0),
                etag=(getattr(obj, "etag", "") or "").strip('"'),
                content_type="application/octet-stream",
                last_modified=getattr(obj, "last_modified", datetime.now(timezone.utc)) or datetime.now(timezone.utc),
            )

    async def ensure_bucket(self, bucket: str) -> None:
        client = self._ensure()
        try:
            await asyncio.to_thread(client.head_bucket, bucket)
        except Exception:
            await asyncio.to_thread(client.create_bucket, bucket)

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        import tos  # type: ignore
        result = await asyncio.to_thread(
            self._ensure().pre_signed_url,
            tos.HttpMethodType.Http_Method_Get,
            bucket, key,
            expires=ttl_seconds,
        )
        return str(getattr(result, "signed_url", result))

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        import tos  # type: ignore
        result = await asyncio.to_thread(
            self._ensure().pre_signed_url,
            tos.HttpMethodType.Http_Method_Put,
            bucket, key,
            expires=ttl_seconds,
        )
        return str(getattr(result, "signed_url", result))
