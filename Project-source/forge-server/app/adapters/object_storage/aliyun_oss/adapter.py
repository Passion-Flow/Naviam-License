"""Aliyun OSS 适配器（oss2 同步 + asyncio.to_thread 包装）。

oss2 是 Aliyun 官方 Python SDK，仅同步；用 `asyncio.to_thread` 包装。
- 鉴权：oss2.Auth(access_key_id, access_key_secret)
- 资源句柄：oss2.Bucket(auth, endpoint, bucket_name)（按 bucket 一份）
- 我们的 ObjectStorage 接口一把 client 跨多 bucket，本适配器用 `_bucket_cache: dict[str, Bucket]` 缓存。

依赖 oss2 仅在 connect() / 操作时延迟导入；模块导入本身不需要 SDK 在场。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class AliyunOssObjectStorage(ObjectStorage):
    provider_name = "aliyun-oss"

    def __init__(
        self,
        *,
        endpoint: str = "",
        access_key_id: str = "",
        access_key_secret: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._auth: Any | None = None
        self._bucket_cache: dict[str, Any] = {}
        # 测试钩子：当 _bucket_factory 被设置时，由它产 Bucket 句柄（绕过 oss2）
        self._bucket_factory: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "AliyunOssObjectStorage":
        return cls(
            endpoint=settings.object_storage_endpoint,
            access_key_id=settings.object_storage_access_key_id,
            access_key_secret=settings.object_storage_access_key_secret,
        )

    @classmethod
    def from_bucket_factory(cls, factory: Any, *, endpoint: str = "fake") -> "AliyunOssObjectStorage":
        """测试钩子：factory(bucket_name) → bucket-like 对象，绕过 oss2 真依赖。"""
        instance = cls(endpoint=endpoint)
        instance._bucket_factory = factory
        return instance

    async def connect(self) -> None:
        if self._auth is not None or self._bucket_factory is not None:
            return
        import oss2  # type: ignore
        self._auth = oss2.Auth(self._access_key_id, self._access_key_secret)

    async def disconnect(self) -> None:
        self._auth = None
        self._bucket_cache.clear()

    async def health_check(self) -> bool:
        return self._auth is not None or self._bucket_factory is not None

    def _bucket(self, bucket: str) -> Any:
        if bucket in self._bucket_cache:
            return self._bucket_cache[bucket]
        if self._bucket_factory is not None:
            handle = self._bucket_factory(bucket)
        else:
            if self._auth is None:
                raise RuntimeError("Aliyun OSS not connected; call connect() first")
            import oss2  # type: ignore
            handle = oss2.Bucket(self._auth, self._endpoint, bucket)
        self._bucket_cache[bucket] = handle
        return handle

    async def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> ObjectMetadata:
        headers: dict[str, str] = {"Content-Type": content_type}
        if metadata:
            for k, v in metadata.items():
                headers[f"x-oss-meta-{k}"] = v
        result = await asyncio.to_thread(self._bucket(bucket).put_object, key, data, headers=headers)
        etag = (getattr(result, "etag", "") or "").strip('"')
        return ObjectMetadata(
            bucket=bucket, key=key, size=len(data), etag=etag,
            content_type=content_type, last_modified=datetime.now(timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        result = await asyncio.to_thread(self._bucket(bucket).get_object, key)
        # oss2 GetObject 返回流；同步读出
        return await asyncio.to_thread(result.read)

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._bucket(bucket).delete_object, key)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            return bool(await asyncio.to_thread(self._bucket(bucket).object_exists, key))
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        meta = await asyncio.to_thread(self._bucket(bucket).head_object, key)
        return ObjectMetadata(
            bucket=bucket, key=key,
            size=int(getattr(meta, "content_length", 0) or 0),
            etag=(getattr(meta, "etag", "") or "").strip('"'),
            content_type=getattr(meta, "content_type", "application/octet-stream"),
            last_modified=getattr(meta, "last_modified", datetime.now(timezone.utc)),
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        # oss2.ObjectIterator 同步迭代；一次性 collect 再 yield
        def _collect() -> list[Any]:
            handle = self._bucket(bucket)
            if self._bucket_factory is not None:
                return list(handle.list_objects(prefix=prefix))
            import oss2  # type: ignore
            return list(oss2.ObjectIterator(handle, prefix=prefix))
        items = await asyncio.to_thread(_collect)
        for it in items:
            yield ObjectMetadata(
                bucket=bucket,
                key=getattr(it, "key", ""),
                size=int(getattr(it, "size", 0) or 0),
                etag=(getattr(it, "etag", "") or "").strip('"'),
                content_type="application/octet-stream",
                last_modified=getattr(it, "last_modified", datetime.now(timezone.utc)),
            )

    async def ensure_bucket(self, bucket: str) -> None:
        handle = self._bucket(bucket)
        try:
            await asyncio.to_thread(handle.get_bucket_info)
        except Exception:
            await asyncio.to_thread(handle.create_bucket)

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        url = await asyncio.to_thread(self._bucket(bucket).sign_url, "GET", key, ttl_seconds)
        return str(url)

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        url = await asyncio.to_thread(self._bucket(bucket).sign_url, "PUT", key, ttl_seconds)
        return str(url)
