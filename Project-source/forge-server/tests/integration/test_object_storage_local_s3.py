"""Object Storage 两个真实现：local filesystem + S3 (via moto mock)。"""
from __future__ import annotations

from pathlib import Path

import boto3
import pytest

from app.adapters.object_storage.local.adapter import LocalObjectStorage
from app.adapters.object_storage.s3.adapter import S3ObjectStorage


# ────────────────────────────────────────────────────────────
# Local filesystem 模式
# ────────────────────────────────────────────────────────────


@pytest.fixture
async def local_fs(tmp_path: Path):
    storage = LocalObjectStorage(mode="filesystem", local_path=str(tmp_path))
    await storage.connect()
    yield storage
    await storage.disconnect()


@pytest.mark.asyncio
async def test_filesystem_put_get_roundtrip(local_fs: LocalObjectStorage) -> None:
    await local_fs.ensure_bucket("test-bucket")
    meta = await local_fs.put("test-bucket", "hello.txt", b"hello, world")
    assert meta.size == 12
    got = await local_fs.get("test-bucket", "hello.txt")
    assert got == b"hello, world"


@pytest.mark.asyncio
async def test_filesystem_exists_and_delete(local_fs: LocalObjectStorage) -> None:
    await local_fs.put("b", "k", b"data")
    assert await local_fs.exists("b", "k")
    await local_fs.delete("b", "k")
    assert not await local_fs.exists("b", "k")


@pytest.mark.asyncio
async def test_filesystem_head(local_fs: LocalObjectStorage) -> None:
    await local_fs.put("b", "img.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
    meta = await local_fs.head("b", "img.png")
    assert meta.size == 8
    assert meta.content_type == "image/png"
    assert meta.etag and len(meta.etag) == 32  # md5 hex


@pytest.mark.asyncio
async def test_filesystem_list_with_prefix(local_fs: LocalObjectStorage) -> None:
    await local_fs.put("b", "logs/2026-05/a.log", b"a")
    await local_fs.put("b", "logs/2026-05/b.log", b"b")
    await local_fs.put("b", "other/c.txt", b"c")

    logs = [m async for m in local_fs.list_("b", prefix="logs/")]
    assert {m.key for m in logs} == {"logs/2026-05/a.log", "logs/2026-05/b.log"}


@pytest.mark.asyncio
async def test_filesystem_rejects_path_traversal(local_fs: LocalObjectStorage) -> None:
    with pytest.raises(ValueError, match=r"\.\."):
        await local_fs.put("b", "../escape.txt", b"x")


@pytest.mark.asyncio
async def test_filesystem_atomic_write(tmp_path: Path) -> None:
    """tmp 文件中间状态不被 list 看到。"""
    storage = LocalObjectStorage(mode="filesystem", local_path=str(tmp_path))
    await storage.connect()
    await storage.put("b", "k", b"v1")
    await storage.put("b", "k", b"v2")  # 覆盖；中间不应有 .tmp 残留
    keys = [m.key async for m in storage.list_("b")]
    assert keys == ["k"]
    await storage.disconnect()


@pytest.mark.asyncio
async def test_filesystem_presign_returns_local_uri(local_fs: LocalObjectStorage) -> None:
    """filesystem 模式不暴露 HTTP；presign 返回 file:// URI。"""
    await local_fs.put("b", "k", b"data")
    url = await local_fs.presign_get_url("b", "k", ttl_seconds=60)
    assert url.startswith("file://")


@pytest.mark.asyncio
async def test_filesystem_health_check(local_fs: LocalObjectStorage) -> None:
    assert await local_fs.health_check() is True


# ────────────────────────────────────────────────────────────
# S3 (moto in-process mock)
# ────────────────────────────────────────────────────────────


@pytest.fixture
def moto_s3_client():
    from moto import mock_aws
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        yield client


@pytest.fixture
async def s3(moto_s3_client):
    storage = S3ObjectStorage.from_client(moto_s3_client)
    yield storage


@pytest.mark.asyncio
async def test_s3_put_get_roundtrip(s3: S3ObjectStorage) -> None:
    await s3.ensure_bucket("forge-license-files")
    meta = await s3.put("forge-license-files", "lic-1.forge", b"forge-content")
    assert meta.size == 13
    assert await s3.get("forge-license-files", "lic-1.forge") == b"forge-content"


@pytest.mark.asyncio
async def test_s3_exists_and_delete(s3: S3ObjectStorage) -> None:
    await s3.ensure_bucket("forge-test-bucket")
    await s3.put("forge-test-bucket","k", b"x")
    assert await s3.exists("forge-test-bucket","k")
    await s3.delete("forge-test-bucket","k")
    assert not await s3.exists("forge-test-bucket","k")


@pytest.mark.asyncio
async def test_s3_head(s3: S3ObjectStorage) -> None:
    await s3.ensure_bucket("forge-test-bucket")
    await s3.put("forge-test-bucket","k", b"hello", content_type="text/plain")
    meta = await s3.head("forge-test-bucket","k")
    assert meta.size == 5
    assert meta.content_type == "text/plain"


@pytest.mark.asyncio
async def test_s3_list_with_prefix(s3: S3ObjectStorage) -> None:
    await s3.ensure_bucket("forge-test-bucket")
    await s3.put("forge-test-bucket","audit/2026/a", b"1")
    await s3.put("forge-test-bucket","audit/2026/b", b"2")
    await s3.put("forge-test-bucket","other/c", b"3")
    listed = [m async for m in s3.list_("forge-test-bucket",prefix="audit/")]
    assert {m.key for m in listed} == {"audit/2026/a", "audit/2026/b"}


@pytest.mark.asyncio
async def test_s3_presign_url(s3: S3ObjectStorage) -> None:
    await s3.ensure_bucket("forge-test-bucket")
    await s3.put("forge-test-bucket","k", b"x")
    url = await s3.presign_get_url("forge-test-bucket","k", ttl_seconds=120)
    assert url.startswith("http") and "Signature" in url


@pytest.mark.asyncio
async def test_s3_health_check(s3: S3ObjectStorage) -> None:
    assert await s3.health_check() is True
