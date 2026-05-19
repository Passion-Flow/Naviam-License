"""Local Object Storage —— 双模：filesystem（直存路径）/ minio（S3 兼容自托管）。

模式由 settings.object_storage_local_mode 决定：
- filesystem: 直接读写 OBJECT_STORAGE_LOCAL_PATH（无中间服务，开发期最轻量）
- minio: 走 MinIO Python SDK（S3 API），与公有云 S3 行为一致
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import mimetypes
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

from app.adapters.object_storage.interface.protocol import ObjectMetadata, ObjectStorage
from app.settings import Settings


class LocalObjectStorage(ObjectStorage):
    provider_name = "local"

    def __init__(
        self,
        *,
        mode: str,
        local_path: str = "",
        minio_host: str = "",
        minio_port: int = 0,
        minio_username: str = "",
        minio_password: str = "",
    ) -> None:
        if mode not in {"filesystem", "minio"}:
            raise ValueError(f"unsupported local mode: {mode!r}")
        self._mode = mode
        self._root = Path(local_path) if local_path else None
        self._minio_host = minio_host
        self._minio_port = minio_port
        self._minio_username = minio_username
        self._minio_password = minio_password
        self._minio_client: object | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "LocalObjectStorage":
        return cls(
            mode=settings.object_storage_local_mode,
            local_path=settings.object_storage_local_path,
            minio_host=settings.object_storage_local_minio_host,
            minio_port=settings.object_storage_local_minio_port,
            minio_username=settings.object_storage_local_minio_username,
            minio_password=settings.object_storage_local_minio_password,
        )

    # ── 生命周期 ────────────────────────────────────────────
    async def connect(self) -> None:
        if self._mode == "filesystem":
            if self._root is None or not str(self._root):
                raise RuntimeError("OBJECT_STORAGE_LOCAL_PATH must be set for filesystem mode")
            self._root.mkdir(parents=True, exist_ok=True)
            return
        # minio
        from minio import Minio  # 延迟 import 避免 filesystem 模式时强依赖
        if not self._minio_host:
            raise RuntimeError("OBJECT_STORAGE_LOCAL_MINIO_HOST is required for minio mode")
        self._minio_client = Minio(
            endpoint=f"{self._minio_host}:{self._minio_port}",
            access_key=self._minio_username,
            secret_key=self._minio_password,
            secure=False,  # 私有化场景下默认明文；TLS 由前置反代处理
        )

    async def disconnect(self) -> None:
        self._minio_client = None

    async def health_check(self) -> bool:
        if self._mode == "filesystem":
            return self._root is not None and self._root.exists()
        if self._minio_client is None:
            return False
        try:
            await asyncio.to_thread(self._minio_client.list_buckets)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False

    # ── 文件系统模式实现 ────────────────────────────────────
    def _fs_path(self, bucket: str, key: str) -> Path:
        if self._root is None:
            raise RuntimeError("filesystem root not configured")
        # 防 path traversal
        if ".." in Path(key).parts or ".." in Path(bucket).parts:
            raise ValueError("invalid key or bucket: contains '..'")
        return self._root / bucket / key

    def _fs_bucket(self, bucket: str) -> Path:
        if self._root is None:
            raise RuntimeError("filesystem root not configured")
        return self._root / bucket

    @staticmethod
    def _guess_content_type(key: str) -> str:
        guess, _ = mimetypes.guess_type(key)
        return guess or "application/octet-stream"

    # ── 接口实现 ────────────────────────────────────────────
    async def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> ObjectMetadata:
        if self._mode == "filesystem":
            return await asyncio.to_thread(self._fs_put, bucket, key, data, content_type)
        # minio
        from io import BytesIO
        import datetime as _dt  # noqa: F401
        await asyncio.to_thread(
            self._minio_client.put_object,  # type: ignore[attr-defined]
            bucket, key, BytesIO(data), len(data),
            content_type=content_type,
            metadata=metadata,
        )
        return ObjectMetadata(
            bucket=bucket,
            key=key,
            size=len(data),
            etag=hashlib.md5(data).hexdigest(),
            content_type=content_type,
            last_modified=datetime.now(timezone.utc),
        )

    def _fs_put(self, bucket: str, key: str, data: bytes, content_type: str) -> ObjectMetadata:
        path = self._fs_path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 原子写
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        stat = path.stat()
        return ObjectMetadata(
            bucket=bucket,
            key=key,
            size=stat.st_size,
            etag=hashlib.md5(data).hexdigest(),
            content_type=content_type or self._guess_content_type(key),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )

    async def get(self, bucket: str, key: str) -> bytes:
        if self._mode == "filesystem":
            return await asyncio.to_thread(self._fs_get, bucket, key)
        response = await asyncio.to_thread(
            self._minio_client.get_object,  # type: ignore[attr-defined]
            bucket, key,
        )
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def _fs_get(self, bucket: str, key: str) -> bytes:
        return self._fs_path(bucket, key).read_bytes()

    async def delete(self, bucket: str, key: str) -> None:
        if self._mode == "filesystem":
            await asyncio.to_thread(self._fs_delete, bucket, key)
            return
        await asyncio.to_thread(
            self._minio_client.remove_object,  # type: ignore[attr-defined]
            bucket, key,
        )

    def _fs_delete(self, bucket: str, key: str) -> None:
        path = self._fs_path(bucket, key)
        if path.exists():
            path.unlink()

    async def exists(self, bucket: str, key: str) -> bool:
        if self._mode == "filesystem":
            return await asyncio.to_thread(lambda: self._fs_path(bucket, key).exists())
        try:
            await asyncio.to_thread(
                self._minio_client.stat_object,  # type: ignore[attr-defined]
                bucket, key,
            )
            return True
        except Exception:
            return False

    async def head(self, bucket: str, key: str) -> ObjectMetadata:
        if self._mode == "filesystem":
            return await asyncio.to_thread(self._fs_head, bucket, key)
        stat = await asyncio.to_thread(
            self._minio_client.stat_object,  # type: ignore[attr-defined]
            bucket, key,
        )
        return ObjectMetadata(
            bucket=bucket,
            key=key,
            size=stat.size,
            etag=stat.etag.strip('"'),
            content_type=stat.content_type or "application/octet-stream",
            last_modified=stat.last_modified or datetime.now(timezone.utc),
        )

    def _fs_head(self, bucket: str, key: str) -> ObjectMetadata:
        path = self._fs_path(bucket, key)
        if not path.exists():
            raise FileNotFoundError(f"object not found: {bucket}/{key}")
        data = path.read_bytes()
        stat = path.stat()
        return ObjectMetadata(
            bucket=bucket,
            key=key,
            size=stat.st_size,
            etag=hashlib.md5(data).hexdigest(),
            content_type=self._guess_content_type(key),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )

    async def list_(self, bucket: str, prefix: str = "") -> AsyncIterator[ObjectMetadata]:
        if self._mode == "filesystem":
            for item in await asyncio.to_thread(self._fs_list, bucket, prefix):
                yield item
            return
        # minio
        objects = await asyncio.to_thread(
            lambda: list(self._minio_client.list_objects(bucket, prefix=prefix, recursive=True))  # type: ignore[attr-defined]
        )
        for obj in objects:
            yield ObjectMetadata(
                bucket=bucket,
                key=obj.object_name,
                size=obj.size or 0,
                etag=(obj.etag or "").strip('"'),
                content_type=obj.content_type or "application/octet-stream",
                last_modified=obj.last_modified or datetime.now(timezone.utc),
            )

    def _fs_list(self, bucket: str, prefix: str) -> list[ObjectMetadata]:
        bucket_dir = self._fs_bucket(bucket)
        if not bucket_dir.exists():
            return []
        results: list[ObjectMetadata] = []
        for path in bucket_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(bucket_dir).as_posix()
            if prefix and not rel.startswith(prefix):
                continue
            data = path.read_bytes()
            stat = path.stat()
            results.append(ObjectMetadata(
                bucket=bucket,
                key=rel,
                size=stat.st_size,
                etag=hashlib.md5(data).hexdigest(),
                content_type=self._guess_content_type(rel),
                last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            ))
        return results

    async def ensure_bucket(self, bucket: str) -> None:
        if self._mode == "filesystem":
            await asyncio.to_thread(lambda: self._fs_bucket(bucket).mkdir(parents=True, exist_ok=True))
            return
        # minio
        exists = await asyncio.to_thread(self._minio_client.bucket_exists, bucket)  # type: ignore[attr-defined]
        if not exists:
            await asyncio.to_thread(self._minio_client.make_bucket, bucket)  # type: ignore[attr-defined]

    async def presign_get_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        if self._mode == "filesystem":
            # filesystem 模式没有 HTTP 暴露；返回本地路径 URI 用作占位
            return f"file://{self._fs_path(bucket, key).absolute()}"
        url = await asyncio.to_thread(
            self._minio_client.presigned_get_object,  # type: ignore[attr-defined]
            bucket, key, expires=timedelta(seconds=ttl_seconds),
        )
        return str(url)

    async def presign_put_url(self, bucket: str, key: str, *, ttl_seconds: int) -> str:
        if self._mode == "filesystem":
            return f"file://{self._fs_path(bucket, key).absolute()}"
        url = await asyncio.to_thread(
            self._minio_client.presigned_put_object,  # type: ignore[attr-defined]
            bucket, key, expires=timedelta(seconds=ttl_seconds),
        )
        return str(url)
