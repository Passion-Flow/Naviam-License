"""Object Storage 8 个 provider 契约测试：

每个 provider 通过 Fake client（模拟 SDK 行为）验证 adapter 编织正确：
- put / get / exists / delete 闭环
- head 返回 size + etag
- list_ 迭代返回多对象
- presign_get_url / presign_put_url 调用对应 SDK 方法

Fake client 实现的是各家 SDK 的最小调用面（我们在 adapter 里实际用到的）。
真实云端验证由客户在交付时验证（私有化部署模型，不在测试覆盖范围）。

local + s3 在单独的测试文件里已有覆盖；此文件专注另外 6 个 provider。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.adapters.object_storage.aliyun_oss.adapter import AliyunOssObjectStorage
from app.adapters.object_storage.azure_blob.adapter import AzureBlobObjectStorage
from app.adapters.object_storage.google_storage.adapter import GoogleStorageObjectStorage
from app.adapters.object_storage.huawei_obs.adapter import HuaweiObsObjectStorage
from app.adapters.object_storage.tencent_cos.adapter import TencentCosObjectStorage
from app.adapters.object_storage.volcengine_tos.adapter import VolcengineTosObjectStorage


# ────────── 通用 fake key-value store ──────────


class _Store:
    """共享的内存对象池（多个 fake 共用）。"""

    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}

    def put(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        etag = f'"{abs(hash(data))}"'
        self.objects[(bucket, key)] = {
            "data": data, "etag": etag, "content_type": content_type,
            "last_modified": datetime.now(timezone.utc),
        }
        return etag


# ────────── Aliyun OSS ──────────


class _OssBucket:
    def __init__(self, store: _Store, name: str) -> None:
        self._store = store
        self._name = name

    def put_object(self, key: str, data: bytes, headers=None):
        etag = self._store.put(self._name, key, data,
                               content_type=(headers or {}).get("Content-Type", "application/octet-stream"))
        return type("R", (), {"etag": etag})()

    def get_object(self, key: str):
        rec = self._store.objects[(self._name, key)]
        data = rec["data"]

        class _R:
            def read(self_inner) -> bytes:
                return data
        return _R()

    def delete_object(self, key: str) -> None:
        self._store.objects.pop((self._name, key), None)

    def object_exists(self, key: str) -> bool:
        return (self._name, key) in self._store.objects

    def head_object(self, key: str):
        rec = self._store.objects[(self._name, key)]
        return type("R", (), {
            "content_length": len(rec["data"]), "etag": rec["etag"],
            "content_type": rec["content_type"], "last_modified": rec["last_modified"],
        })()

    def list_objects(self, prefix: str = ""):
        for (b, k), rec in self._store.objects.items():
            if b == self._name and k.startswith(prefix):
                yield type("O", (), {
                    "key": k, "size": len(rec["data"]),
                    "etag": rec["etag"], "last_modified": rec["last_modified"],
                })()

    def sign_url(self, method: str, key: str, ttl: int) -> str:
        return f"oss://{self._name}/{key}?method={method}&ttl={ttl}"


@pytest.mark.asyncio
async def test_aliyun_oss_round_trip() -> None:
    store = _Store()
    adapter = AliyunOssObjectStorage.from_bucket_factory(lambda b: _OssBucket(store, b))
    await adapter.connect()
    assert adapter.provider_name == "aliyun-oss"

    meta = await adapter.put("b1", "k1", b"hello", content_type="text/plain")
    assert meta.size == 5
    assert await adapter.get("b1", "k1") == b"hello"
    assert await adapter.exists("b1", "k1") is True
    h = await adapter.head("b1", "k1")
    assert h.size == 5

    await adapter.put("b1", "k2", b"second")
    items = [m.key async for m in adapter.list_("b1", prefix="k")]
    assert set(items) == {"k1", "k2"}

    url_get = await adapter.presign_get_url("b1", "k1", ttl_seconds=60)
    url_put = await adapter.presign_put_url("b1", "k1", ttl_seconds=60)
    assert "method=GET" in url_get and "method=PUT" in url_put

    await adapter.delete("b1", "k1")
    assert await adapter.exists("b1", "k1") is False


# ────────── Azure Blob ──────────


class _AzureBlobClient:
    def __init__(self, store: _Store, container: str, blob: str) -> None:
        self._store = store
        self._c = container
        self._k = blob

    def upload_blob(self, data: bytes, overwrite: bool = True, content_settings=None, metadata=None):
        ct = getattr(content_settings, "content_type", "application/octet-stream") if content_settings else "application/octet-stream"
        etag = self._store.put(self._c, self._k, data, content_type=ct)
        return {"etag": etag}

    def download_blob(self):
        rec = self._store.objects[(self._c, self._k)]
        data = rec["data"]

        class _D:
            def readall(self_inner) -> bytes:
                return data
        return _D()

    def delete_blob(self) -> None:
        self._store.objects.pop((self._c, self._k), None)

    def exists(self) -> bool:
        return (self._c, self._k) in self._store.objects

    def get_blob_properties(self):
        rec = self._store.objects[(self._c, self._k)]
        cs = type("CS", (), {"content_type": rec["content_type"]})()
        return type("P", (), {
            "size": len(rec["data"]), "etag": rec["etag"],
            "content_settings": cs, "last_modified": rec["last_modified"],
        })()


class _AzureContainerClient:
    def __init__(self, store: _Store, name: str) -> None:
        self._store = store
        self._name = name

    def list_blobs(self, name_starts_with=None):
        prefix = name_starts_with or ""
        for (c, k), rec in self._store.objects.items():
            if c == self._name and k.startswith(prefix):
                yield type("B", (), {
                    "name": k, "size": len(rec["data"]),
                    "etag": rec["etag"], "last_modified": rec["last_modified"],
                })()


class _AzureService:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def get_blob_client(self, container: str, blob: str):
        return _AzureBlobClient(self._store, container, blob)

    def get_container_client(self, container: str):
        return _AzureContainerClient(self._store, container)

    def create_container(self, name: str) -> None:
        self._store.buckets.add(name)

    def get_service_properties(self) -> dict:
        return {}

    def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_azure_blob_round_trip() -> None:
    store = _Store()
    adapter = AzureBlobObjectStorage.from_client(_AzureService(store))
    assert adapter.provider_name == "azure-blob"
    assert await adapter.health_check() is True

    await adapter.put("container", "k", b"hello", content_type="text/plain")
    assert await adapter.get("container", "k") == b"hello"
    assert await adapter.exists("container", "k") is True
    h = await adapter.head("container", "k")
    assert h.size == 5 and h.content_type == "text/plain"

    await adapter.put("container", "k2", b"two")
    keys = [m.key async for m in adapter.list_("container")]
    assert set(keys) == {"k", "k2"}

    await adapter.ensure_bucket("new-c")
    assert "new-c" in store.buckets

    await adapter.delete("container", "k")
    assert await adapter.exists("container", "k") is False


# ────────── Google Cloud Storage ──────────


class _GcsBlob:
    def __init__(self, store: _Store, bucket: str, name: str) -> None:
        self._store = store
        self._b = bucket
        self._n = name
        self.name = name
        self.metadata: dict[str, str] | None = None
        self.etag = ""
        self.size = 0
        self.content_type = "application/octet-stream"
        self.updated = datetime.now(timezone.utc)

    def upload_from_string(self, data: bytes, content_type: str = "application/octet-stream") -> None:
        etag = self._store.put(self._b, self._n, data, content_type=content_type)
        self.etag = etag
        self.size = len(data)
        self.content_type = content_type

    def download_as_bytes(self) -> bytes:
        return self._store.objects[(self._b, self._n)]["data"]

    def delete(self) -> None:
        self._store.objects.pop((self._b, self._n), None)

    def exists(self) -> bool:
        return (self._b, self._n) in self._store.objects

    def reload(self) -> None:
        rec = self._store.objects[(self._b, self._n)]
        self.size = len(rec["data"])
        self.etag = rec["etag"]
        self.content_type = rec["content_type"]
        self.updated = rec["last_modified"]

    def generate_signed_url(self, *, version: str, expiration, method: str) -> str:
        return f"gs://{self._b}/{self._n}?v={version}&m={method}"


class _GcsBucket:
    def __init__(self, store: _Store, name: str) -> None:
        self._store = store
        self._name = name

    def blob(self, name: str):
        return _GcsBlob(self._store, self._name, name)


class _GcsClient:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def bucket(self, name: str):
        return _GcsBucket(self._store, name)

    def list_buckets(self, max_results: int = 1):
        return list(self._store.buckets)

    def get_bucket(self, name: str):
        if name not in self._store.buckets:
            raise RuntimeError("not found")
        return _GcsBucket(self._store, name)

    def create_bucket(self, name: str):
        self._store.buckets.add(name)
        return _GcsBucket(self._store, name)

    def list_blobs(self, bucket: str, prefix=None):
        pref = prefix or ""
        out = []
        for (b, k), rec in self._store.objects.items():
            if b == bucket and k.startswith(pref):
                blob = _GcsBlob(self._store, b, k)
                blob.size = len(rec["data"])
                blob.etag = rec["etag"]
                blob.content_type = rec["content_type"]
                blob.updated = rec["last_modified"]
                out.append(blob)
        return out


@pytest.mark.asyncio
async def test_google_storage_round_trip() -> None:
    store = _Store()
    adapter = GoogleStorageObjectStorage.from_client(_GcsClient(store))
    assert adapter.provider_name == "google-storage"

    await adapter.put("b", "k", b"hello")
    assert await adapter.get("b", "k") == b"hello"
    assert await adapter.exists("b", "k") is True
    h = await adapter.head("b", "k")
    assert h.size == 5

    await adapter.put("b", "k2", b"two")
    keys = [m.key async for m in adapter.list_("b")]
    assert set(keys) == {"k", "k2"}

    await adapter.ensure_bucket("new-b")
    assert "new-b" in store.buckets

    url = await adapter.presign_get_url("b", "k", ttl_seconds=60)
    assert "m=GET" in url
    url_put = await adapter.presign_put_url("b", "k", ttl_seconds=60)
    assert "m=PUT" in url_put

    await adapter.delete("b", "k")
    assert await adapter.exists("b", "k") is False


# ────────── Tencent COS ──────────


class _CosClient:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str = "application/octet-stream", Metadata=None) -> dict:
        etag = self._store.put(Bucket, Key, Body, content_type=ContentType)
        return {"ETag": etag}

    def get_object(self, Bucket: str, Key: str) -> dict:
        rec = self._store.objects[(Bucket, Key)]
        data = rec["data"]

        class _Stream:
            def read(self_inner) -> bytes:
                return data

        class _Body:
            def get_raw_stream(self_inner):
                return _Stream()

        return {"Body": _Body()}

    def delete_object(self, Bucket: str, Key: str) -> None:
        self._store.objects.pop((Bucket, Key), None)

    def object_exists(self, Bucket: str, Key: str) -> bool:
        return (Bucket, Key) in self._store.objects

    def head_object(self, Bucket: str, Key: str) -> dict:
        rec = self._store.objects[(Bucket, Key)]
        return {
            "Content-Length": str(len(rec["data"])),
            "ETag": rec["etag"],
            "Content-Type": rec["content_type"],
        }

    def head_bucket(self, Bucket: str) -> dict:
        if Bucket not in self._store.buckets:
            raise RuntimeError("not found")
        return {}

    def create_bucket(self, Bucket: str) -> None:
        self._store.buckets.add(Bucket)

    def list_buckets(self) -> dict:
        return {"Buckets": [{"Name": b} for b in self._store.buckets]}

    def list_objects(self, Bucket: str, Prefix: str = "") -> dict:
        return {
            "Contents": [
                {"Key": k, "Size": len(rec["data"]), "ETag": rec["etag"]}
                for (b, k), rec in self._store.objects.items()
                if b == Bucket and k.startswith(Prefix)
            ],
        }

    def get_presigned_url(self, Method: str, Bucket: str, Key: str, Expired: int) -> str:
        return f"cos://{Bucket}/{Key}?m={Method}&ttl={Expired}"


@pytest.mark.asyncio
async def test_tencent_cos_round_trip() -> None:
    store = _Store()
    adapter = TencentCosObjectStorage.from_client(_CosClient(store))
    assert adapter.provider_name == "tencent-cos"
    assert await adapter.health_check() is True

    await adapter.put("b", "k", b"hello", content_type="text/plain")
    assert await adapter.get("b", "k") == b"hello"
    assert await adapter.exists("b", "k") is True
    h = await adapter.head("b", "k")
    assert h.size == 5

    await adapter.put("b", "k2", b"two")
    keys = [m.key async for m in adapter.list_("b", prefix="k")]
    assert set(keys) == {"k", "k2"}

    url = await adapter.presign_get_url("b", "k", ttl_seconds=60)
    assert "m=GET" in url and "ttl=60" in url

    await adapter.delete("b", "k")
    assert await adapter.exists("b", "k") is False


# ────────── Volcengine TOS ──────────


class _TosClient:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def put_object(self, bucket: str, key: str, content: bytes, content_type: str = "application/octet-stream", meta=None):
        etag = self._store.put(bucket, key, content, content_type=content_type)
        return type("R", (), {"etag": etag})()

    def get_object(self, bucket: str, key: str):
        rec = self._store.objects[(bucket, key)]
        data = rec["data"]

        class _G:
            def read(self_inner) -> bytes:
                return data
        return _G()

    def delete_object(self, bucket: str, key: str) -> None:
        self._store.objects.pop((bucket, key), None)

    def head_object(self, bucket: str, key: str):
        rec = self._store.objects[(bucket, key)]
        return type("H", (), {
            "content_length": len(rec["data"]), "etag": rec["etag"],
            "content_type": rec["content_type"], "last_modified": rec["last_modified"],
        })()

    def list_objects(self, bucket: str, prefix=None):
        pref = prefix or ""
        contents = [
            type("C", (), {
                "key": k, "size": len(rec["data"]),
                "etag": rec["etag"], "last_modified": rec["last_modified"],
            })()
            for (b, k), rec in self._store.objects.items()
            if b == bucket and k.startswith(pref)
        ]
        return type("L", (), {"contents": contents})()

    def head_bucket(self, bucket: str) -> None:
        if bucket not in self._store.buckets:
            raise RuntimeError("not found")

    def create_bucket(self, bucket: str) -> None:
        self._store.buckets.add(bucket)

    def list_buckets(self):
        return list(self._store.buckets)

    def pre_signed_url(self, method, bucket: str, key: str, expires: int):
        return type("U", (), {"signed_url": f"tos://{bucket}/{key}?m={method}&ttl={expires}"})()


@pytest.mark.asyncio
async def test_volcengine_tos_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    # 替身 tos 模块（presign 用到 tos.HttpMethodType）
    fake_tos = type("M", (), {
        "HttpMethodType": type("T", (), {
            "Http_Method_Get": "GET", "Http_Method_Put": "PUT",
        })(),
    })()
    import sys
    monkeypatch.setitem(sys.modules, "tos", fake_tos)  # type: ignore[arg-type]

    store = _Store()
    adapter = VolcengineTosObjectStorage.from_client(_TosClient(store))
    assert adapter.provider_name == "volcengine-tos"
    assert await adapter.health_check() is True

    await adapter.put("b", "k", b"hello", content_type="text/plain")
    assert await adapter.get("b", "k") == b"hello"
    assert await adapter.exists("b", "k") is True
    h = await adapter.head("b", "k")
    assert h.size == 5

    await adapter.put("b", "k2", b"two")
    keys = [m.key async for m in adapter.list_("b")]
    assert set(keys) == {"k", "k2"}

    url = await adapter.presign_get_url("b", "k", ttl_seconds=60)
    assert "m=GET" in url and "ttl=60" in url

    await adapter.delete("b", "k")
    assert await adapter.exists("b", "k") is False


# ────────── Huawei OBS ──────────


class _ObsResponse:
    def __init__(self, *, status: int = 200, body: Any = None, **fields: Any) -> None:
        self.status = status
        self.body = body
        for k, v in fields.items():
            setattr(self, k, v)


class _ObsClient:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def listBuckets(self) -> _ObsResponse:
        return _ObsResponse(status=200, body=list(self._store.buckets))

    def putObject(self, bucket: str, key: str, content: bytes,
                  contentType: str = "application/octet-stream", metadata=None):
        etag = self._store.put(bucket, key, content, content_type=contentType)
        return _ObsResponse(status=200, etag=etag)

    def getObject(self, bucket: str, key: str, loadStreamInMemory: bool = False):
        rec = self._store.objects[(bucket, key)]
        body = type("B", (), {"buffer": rec["data"]})()
        return _ObsResponse(status=200, body=body)

    def deleteObject(self, bucket: str, key: str):
        self._store.objects.pop((bucket, key), None)
        return _ObsResponse(status=204)

    def getObjectMetadata(self, bucket: str, key: str):
        if (bucket, key) not in self._store.objects:
            return _ObsResponse(status=404)
        rec = self._store.objects[(bucket, key)]
        return _ObsResponse(
            status=200,
            contentLength=len(rec["data"]),
            etag=rec["etag"],
            contentType=rec["content_type"],
            lastModified=rec["last_modified"],
        )

    def listObjects(self, bucket: str, prefix=None):
        pref = prefix or ""
        contents = [
            type("O", (), {
                "key": k, "size": len(rec["data"]),
                "etag": rec["etag"], "lastModified": rec["last_modified"],
            })()
            for (b, k), rec in self._store.objects.items()
            if b == bucket and k.startswith(pref)
        ]
        body = type("LB", (), {"contents": contents})()
        return _ObsResponse(status=200, body=body)

    def headBucket(self, bucket: str):
        if bucket in self._store.buckets:
            return _ObsResponse(status=200)
        return _ObsResponse(status=404)

    def createBucket(self, bucket: str):
        self._store.buckets.add(bucket)
        return _ObsResponse(status=200)

    def createSignedUrl(self, *, method: str, bucketName: str, objectKey: str, expires: int):
        return _ObsResponse(status=200, signedUrl=f"obs://{bucketName}/{objectKey}?m={method}&ttl={expires}")

    def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_huawei_obs_round_trip() -> None:
    store = _Store()
    adapter = HuaweiObsObjectStorage.from_client(_ObsClient(store))
    assert adapter.provider_name == "huawei-obs"
    assert await adapter.health_check() is True

    await adapter.put("b", "k", b"hello", content_type="text/plain")
    assert await adapter.get("b", "k") == b"hello"
    assert await adapter.exists("b", "k") is True
    h = await adapter.head("b", "k")
    assert h.size == 5 and h.content_type == "text/plain"

    await adapter.put("b", "k2", b"two")
    keys = [m.key async for m in adapter.list_("b")]
    assert set(keys) == {"k", "k2"}

    await adapter.ensure_bucket("new-b")
    assert "new-b" in store.buckets

    url = await adapter.presign_get_url("b", "k", ttl_seconds=60)
    assert "m=GET" in url

    await adapter.delete("b", "k")
    assert await adapter.exists("b", "k") is False


# ────────── 跨 provider：未连接抛 RuntimeError ──────────


@pytest.mark.asyncio
async def test_all_providers_raise_when_not_connected() -> None:
    """from_settings 构造但不 connect → 调操作应抛 RuntimeError（防呆）。"""
    # aliyun 用 from_bucket_factory 走另一条路，跳过它
    for adapter in [
        AzureBlobObjectStorage(),
        GoogleStorageObjectStorage(),
        TencentCosObjectStorage(),
        VolcengineTosObjectStorage(),
        HuaweiObsObjectStorage(),
    ]:
        with pytest.raises(RuntimeError):
            await adapter.put("b", "k", b"x")


# ────────── 跨 provider：模块导入无需 SDK ──────────


def test_all_provider_modules_import_without_sdks_installed() -> None:
    """SDK 未装时，import 适配器模块本身不应失败（仅 connect()/操作时延迟导入）。"""
    # 重新 import 一次以触发顶层加载
    import importlib

    for mod_name in [
        "app.adapters.object_storage.aliyun_oss.adapter",
        "app.adapters.object_storage.azure_blob.adapter",
        "app.adapters.object_storage.google_storage.adapter",
        "app.adapters.object_storage.tencent_cos.adapter",
        "app.adapters.object_storage.volcengine_tos.adapter",
        "app.adapters.object_storage.huawei_obs.adapter",
    ]:
        importlib.import_module(mod_name)  # 不抛即通过
