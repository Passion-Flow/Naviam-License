"""AWS S3 适配器（boto3 同步 + asyncio.to_thread 包装）。

为什么不用 aioboto3：
- boto3 + asyncio.to_thread 已经足够；aioboto3 会引入 aiobotocore 兼容性问题
- 包大小考量；boto3 在 Python 生态最稳

也可适配 S3-compatible：通过 OBJECT_STORAGE_ENDPOINT 指向 MinIO / Ceph / 等。
"""
from __future__ import annotations

import asyncio
import datetime
from datetime import datetime as dt_class
from datetime import timezone
from typing import Any, AsyncIterator

import boto3
from botocore.client import Config

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class S3ObjectStorage(ObjectStorage):
    provider_name = "s3"

    def __init__(
        self,
        *,
        endpoint: str = "",
        region: str = "us-east-1",
        access_key_id: str = "",
        access_key_secret: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._region = region
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._client: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3ObjectStorage":
        return cls(
            endpoint=settings.object_storage_endpoint,
            region=settings.object_storage_region or "us-east-1",
            access_key_id=settings.object_storage_access_key_id,
            access_key_secret=settings.object_storage_access_key_secret,
        )

    @classmethod
    def from_client(cls, client: Any) -> "S3ObjectStorage":
        """测试钩子：注入 moto/boto3 client。"""
        instance = cls.__new__(cls)
        instance._endpoint = ""
        instance._region = "us-east-1"
        instance._access_key_id = ""
        instance._access_key_secret = ""
        instance._client = client
        return instance

    async def connect(self) -> None:
        if self._client is not None:
            return
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": self._region,
            "aws_access_key_id": self._access_key_id,
            "aws_secret_access_key": self._access_key_secret,
            "config": Config(signature_version="s3v4"),
        }
        if self._endpoint:
            kwargs["endpoint_url"] = self._endpoint
        self._client = await asyncio.to_thread(boto3.client, **kwargs)

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

    def _ensure(self):
        if self._client is None:
            raise RuntimeError("S3 client not connected; call connect() first")
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
        return ObjectMetadata(
            bucket=bucket,
            key=key,
            size=len(data),
            etag=(response.get("ETag") or "").strip('"'),
            content_type=content_type,
            last_modified=dt_class.now(timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        response = await asyncio.to_thread(self._ensure().get_object, Bucket=bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._ensure().delete_object, Bucket=bucket, Key=key)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            await asyncio.to_thread(self._ensure().head_object, Bucket=bucket, Key=key)
            return True
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        response = await asyncio.to_thread(self._ensure().head_object, Bucket=bucket, Key=key)
        last_modified = response.get("LastModified")
        if last_modified is None:
            last_modified = dt_class.now(timezone.utc)
        return ObjectMetadata(
            bucket=bucket,
            key=key,
            size=int(response.get("ContentLength", 0)),
            etag=(response.get("ETag") or "").strip('"'),
            content_type=response.get("ContentType", "application/octet-stream"),
            last_modified=last_modified,
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        paginator = self._ensure().get_paginator("list_objects_v2")
        pages = await asyncio.to_thread(
            lambda: list(paginator.paginate(Bucket=bucket, Prefix=prefix))
        )
        for page in pages:
            for obj in page.get("Contents", []):
                yield ObjectMetadata(
                    bucket=bucket,
                    key=obj["Key"],
                    size=obj.get("Size", 0),
                    etag=(obj.get("ETag") or "").strip('"'),
                    content_type="application/octet-stream",
                    last_modified=obj.get("LastModified") or dt_class.now(timezone.utc),
                )

    async def ensure_bucket(self, bucket: str) -> None:
        client = self._ensure()
        try:
            await asyncio.to_thread(client.head_bucket, Bucket=bucket)
        except Exception:
            # us-east-1 不接受 LocationConstraint
            kwargs: dict[str, Any] = {"Bucket": bucket}
            if self._region and self._region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
            await asyncio.to_thread(client.create_bucket, **kwargs)

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        url = await asyncio.to_thread(
            self._ensure().generate_presigned_url,
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
        return str(url)

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        url = await asyncio.to_thread(
            self._ensure().generate_presigned_url,
            "put_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
        return str(url)
