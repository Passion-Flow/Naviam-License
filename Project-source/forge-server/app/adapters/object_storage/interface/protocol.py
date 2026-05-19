"""Object Storage 适配器统一接口。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Protocol


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    bucket: str
    key: str
    size: int
    etag: str
    content_type: str
    last_modified: datetime


class ObjectStorage(Protocol):
    """Object Storage 适配器统一接口。8 个 provider 必须全部实现。

    本接口刻意保持 **provider 中立**：不暴露任何 boto3 / oss2 / 等具体 SDK 的对象。
    """

    @property
    def provider_name(self) -> str: ...

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health_check(self) -> bool: ...

    # 基础对象操作
    async def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> ObjectMetadata: ...

    async def get(self, bucket: str, key: str) -> bytes: ...

    async def delete(self, bucket: str, key: str) -> None: ...

    async def exists(self, bucket: str, key: str) -> bool: ...

    async def head(self, bucket: str, key: str) -> ObjectMetadata: ...

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]: ...

    # Bucket 操作（开发期可调，生产由客户在交付前创建）
    async def ensure_bucket(self, bucket: str) -> None: ...

    # 预签名 URL（用于客户端直传 / 直下）
    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str: ...
    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str: ...
