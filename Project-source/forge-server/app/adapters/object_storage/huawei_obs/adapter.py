"""Huawei OBS 适配器（esdk-obs-python 同步 + asyncio.to_thread 包装）。

华为云 OBS Python SDK：
    from obs import ObsClient
    client = ObsClient(access_key_id, secret_access_key, server=endpoint)
    client.putObject(bucketName, objectKey, content=data, metadata=...)
    client.getObject(bucketName, objectKey, loadStreamInMemory=True)
    client.createSignedUrl(method='GET', bucketName=..., objectKey=..., expires=...)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class HuaweiObsObjectStorage(ObjectStorage):
    provider_name = "huawei-obs"

    def __init__(
        self,
        *,
        endpoint: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "HuaweiObsObjectStorage":
        return cls(
            endpoint=settings.object_storage_endpoint,
            access_key_id=settings.object_storage_access_key_id,
            secret_access_key=settings.object_storage_access_key_secret,
        )

    @classmethod
    def from_client(cls, client: Any) -> "HuaweiObsObjectStorage":
        instance = cls()
        instance._client = client
        return instance

    async def connect(self) -> None:
        if self._client is not None:
            return
        from obs import ObsClient  # type: ignore
        self._client = await asyncio.to_thread(
            ObsClient,
            access_key_id=self._access_key_id,
            secret_access_key=self._secret_access_key,
            server=self._endpoint,
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
            resp = await asyncio.to_thread(self._client.listBuckets)
            return _status_ok(resp)
        except Exception:
            return False

    def _ensure(self) -> Any:
        if self._client is None:
            raise RuntimeError("Huawei OBS not connected; call connect() first")
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
        kwargs: dict[str, Any] = {"content": data, "contentType": content_type}
        if metadata:
            kwargs["metadata"] = metadata
        resp = await asyncio.to_thread(self._ensure().putObject, bucket, key, **kwargs)
        etag = _resp_attr(resp, "etag", "").strip('"')
        return ObjectMetadata(
            bucket=bucket, key=key, size=len(data), etag=etag,
            content_type=content_type, last_modified=datetime.now(timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        resp = await asyncio.to_thread(
            self._ensure().getObject, bucket, key, loadStreamInMemory=True,
        )
        body = _resp_attr(resp, "body", None)
        if body is None:
            return b""
        # 内存模式下 body.buffer 是 bytes
        buf = getattr(body, "buffer", None)
        if isinstance(buf, (bytes, bytearray)):
            return bytes(buf)
        # 退化：尝试 read()
        if hasattr(body, "read"):
            return await asyncio.to_thread(body.read)
        return bytes(body) if isinstance(body, (bytes, bytearray)) else b""

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._ensure().deleteObject, bucket, key)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            resp = await asyncio.to_thread(self._ensure().getObjectMetadata, bucket, key)
            return _status_ok(resp)
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        resp = await asyncio.to_thread(self._ensure().getObjectMetadata, bucket, key)
        size = int(_resp_attr(resp, "contentLength", 0) or 0)
        etag = _resp_attr(resp, "etag", "").strip('"')
        content_type = _resp_attr(resp, "contentType", "application/octet-stream") or "application/octet-stream"
        last_modified = _resp_attr(resp, "lastModified", None) or datetime.now(timezone.utc)
        return ObjectMetadata(
            bucket=bucket, key=key, size=size, etag=etag,
            content_type=content_type, last_modified=last_modified,
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        resp = await asyncio.to_thread(
            self._ensure().listObjects, bucket, prefix=prefix or None,
        )
        body = _resp_attr(resp, "body", None)
        contents = getattr(body, "contents", None) or []
        for obj in contents:
            yield ObjectMetadata(
                bucket=bucket,
                key=getattr(obj, "key", ""),
                size=int(getattr(obj, "size", 0) or 0),
                etag=(getattr(obj, "etag", "") or "").strip('"'),
                content_type="application/octet-stream",
                last_modified=getattr(obj, "lastModified", datetime.now(timezone.utc)) or datetime.now(timezone.utc),
            )

    async def ensure_bucket(self, bucket: str) -> None:
        client = self._ensure()
        try:
            resp = await asyncio.to_thread(client.headBucket, bucket)
            if _status_ok(resp):
                return
        except Exception:
            pass
        await asyncio.to_thread(client.createBucket, bucket)

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        resp = await asyncio.to_thread(
            self._ensure().createSignedUrl,
            method="GET",
            bucketName=bucket,
            objectKey=key,
            expires=ttl_seconds,
        )
        return str(_resp_attr(resp, "signedUrl", resp))

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        resp = await asyncio.to_thread(
            self._ensure().createSignedUrl,
            method="PUT",
            bucketName=bucket,
            objectKey=key,
            expires=ttl_seconds,
        )
        return str(_resp_attr(resp, "signedUrl", resp))


def _status_ok(resp: Any) -> bool:
    status = getattr(resp, "status", None)
    if status is None:
        return True
    return 200 <= int(status) < 300


def _resp_attr(resp: Any, name: str, default: Any) -> Any:
    """OBS SDK 返回的对象有 .body 子对象 + 顶层属性混用，统一兜底取值。"""
    if resp is None:
        return default
    if hasattr(resp, name):
        v = getattr(resp, name)
        if v is not None:
            return v
    body = getattr(resp, "body", None)
    if body is not None and hasattr(body, name):
        v = getattr(body, name)
        if v is not None:
            return v
    return default
