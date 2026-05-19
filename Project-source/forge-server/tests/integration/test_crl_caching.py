"""CRL HTTP caching 端到端：
- 200 响应永远带 ETag + Cache-Control
- 同样 ETag 的 If-None-Match → 304 + 空 body + 同样的 cache headers
- revoke 后 ETag 变化，旧 ETag 不再 304
- unrevoke 后 ETag 再次变化
- 内容未变时**不递增 sequence / 不重复签名**（用 fake key_storage 计数 load 调用次数）
- 多次同 ETag 请求只触发一次签名 + 一次 next_sequence
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fakeredis import aioredis as fakeredis_async
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.cache.redis.adapter import RedisCache
from app.adapters.database.postgres.adapter import PostgresDatabase
from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import CrlManager
from app.core.license.crl.manager import InMemoryRevocationStore
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.middleware.api_key_auth import API_KEY_HEADER
from app.models import Base
from app.repositories import (
    ApiKeyRepository,
    AuditLogRepository,
    DbBackedApiKeyAuth,
    DbBackedRevocationStore,
    LicenseRepository,
    UserRepository,
)
from app.settings import Settings
from app.state import AppState
from app.core.auth import SessionStore


@pytest.fixture
def settings(tmp_path: Path):
    import os
    env = {
        "DATABASE_HOST": "localhost", "DATABASE_PORT": "5432",
        "DATABASE_USERNAME": "test", "DATABASE_PASSWORD": "test", "DATABASE_DATABASE": "test",
        "CACHE_HOST": "localhost", "CACHE_PORT": "6379", "CACHE_PASSWORD": "test",
        "KEY_STORAGE_BACKEND": "local_file",
        "KEY_STORAGE_LOCAL_PATH": str(tmp_path / "keys"),
        "KEY_MASTER_PASSPHRASE": "test-pass",
        "AUTH_SESSION_SECRET": "test-session-xxxxxxxx",
        "OBJECT_STORAGE_TYPE": "local",
    }
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield Settings()  # type: ignore[call-arg]
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield PostgresDatabase.from_engine(engine)
    await engine.dispose()


@pytest.fixture
async def cache():
    fake = fakeredis_async.FakeRedis(decode_responses=False)
    yield RedisCache.from_client(fake, db=1)
    await fake.aclose()


class _CountingKeyStorage:
    """包一层真实的 LocalFileKeyStorage，仅记录 load() 调用次数。"""

    def __init__(self, inner: LocalFileKeyStorage) -> None:
        self._inner = inner
        self.load_count = 0

    async def save(self, record):
        return await self._inner.save(record)

    async def load(self, key_id: str):
        self.load_count += 1
        return await self._inner.load(key_id)

    async def list_ids(self):
        return await self._inner.list_ids()

    async def load_public(self, key_id: str):
        return await self._inner.load_public(key_id)

    async def update_status(self, key_id: str, status):
        return await self._inner.update_status(key_id, status)

    async def delete(self, key_id: str):
        return await self._inner.delete(key_id)


@pytest.fixture
async def app_state(settings, db, cache, tmp_path: Path):
    inner_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )
    await generate_and_save_signing_key(inner_storage, algorithm="ed25519")
    counting_storage = _CountingKeyStorage(inner_storage)

    revocation_store = DbBackedRevocationStore(db)
    user_repo = UserRepository(db)
    await user_repo.create(
        username="admin",
        email="admin@forge.local",
        plaintext_password="correct-horse-battery-staple",
        is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plain = await api_key_repo.issue(customer_id="c", project_label="p")

    state = AppState(
        settings=settings,
        key_storage=counting_storage,  # type: ignore[arg-type]
        revocation_store=revocation_store,
        crl_manager=CrlManager(
            store=revocation_store,
            key_storage=counting_storage,  # type: ignore[arg-type]
            algorithm="ed25519",
        ),
        heartbeat_collector=InMemoryHeartbeatCollector(),
        multi_env_detector=MultiEnvDetector(window=timedelta(hours=24), threshold=1),
        api_keys={},
        database=db,
        license_repository=LicenseRepository(db),
        api_key_auth=DbBackedApiKeyAuth(api_key_repo),
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
        audit_log_repository=AuditLogRepository(db),
    )
    return state, api_plain, counting_storage


@pytest.fixture
async def client(app_state):
    state, _, _ = app_state
    app = create_app(state_builder=lambda: state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


@pytest.fixture
def api_key(app_state) -> str:
    return app_state[1]


@pytest.fixture
def counting_storage(app_state):
    return app_state[2]


CRL_PATH = "/api/v1/revocation-list/ed25519.crl"


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_response_has_etag_and_cache_headers(client: httpx.AsyncClient) -> None:
    r = await client.get(CRL_PATH)
    assert r.status_code == 200
    etag = r.headers["ETag"]
    assert etag.startswith('"') and etag.endswith('"')
    cache_control = r.headers["Cache-Control"]
    assert "max-age=" in cache_control
    assert "must-revalidate" in cache_control
    assert r.headers["Content-Disposition"].endswith('forge-ed25519.crl"')


@pytest.mark.asyncio
async def test_matching_if_none_match_returns_304(client: httpx.AsyncClient) -> None:
    r1 = await client.get(CRL_PATH)
    etag = r1.headers["ETag"]
    r2 = await client.get(CRL_PATH, headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.content == b""
    assert r2.headers["ETag"] == etag
    # 304 仍然要带 Cache-Control 让 verifier 知道还能继续缓存
    assert "max-age=" in r2.headers["Cache-Control"]


@pytest.mark.asyncio
async def test_weak_etag_form_also_matches(client: httpx.AsyncClient) -> None:
    r1 = await client.get(CRL_PATH)
    etag = r1.headers["ETag"]
    # 客户端可能加 W/ 弱前缀
    r2 = await client.get(CRL_PATH, headers={"If-None-Match": f"W/{etag}"})
    assert r2.status_code == 304


@pytest.mark.asyncio
async def test_revoke_changes_etag(client: httpx.AsyncClient, api_key: str) -> None:
    r1 = await client.get(CRL_PATH)
    etag_before = r1.headers["ETag"]

    # 签一份 license 然后吊销，CRL 内容必然变化
    iss = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )
    lid = iss.json()["license_id"]
    await client.post(
        f"/api/v1/licenses/{lid}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "test"},
    )

    r2 = await client.get(CRL_PATH)
    assert r2.headers["ETag"] != etag_before

    # 旧 ETag 不再 304
    r3 = await client.get(CRL_PATH, headers={"If-None-Match": etag_before})
    assert r3.status_code == 200


@pytest.mark.asyncio
async def test_unrevoke_changes_etag_back_to_empty_shape(
    client: httpx.AsyncClient, api_key: str
) -> None:
    """unrevoke 后 CRL 内容回到空集 → ETag 与最初一致。"""
    initial_etag = (await client.get(CRL_PATH)).headers["ETag"]

    iss = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )
    lid = iss.json()["license_id"]
    await client.post(
        f"/api/v1/licenses/{lid}/revoke",
        headers={API_KEY_HEADER: api_key}, json={"reason": "x"},
    )
    await client.post(
        f"/api/v1/licenses/{lid}/unrevoke",
        headers={API_KEY_HEADER: api_key},
    )

    final_etag = (await client.get(CRL_PATH)).headers["ETag"]
    assert final_etag == initial_etag


@pytest.mark.asyncio
async def test_repeated_get_does_not_resign(
    client: httpx.AsyncClient, counting_storage: _CountingKeyStorage
) -> None:
    """同内容多次 GET 只触发一次签名。

    每次 build_crl() 会调用 key_storage.load() 两次（find_active_key_id 扫描 + 签名加载），
    所以 baseline 是 2 / 次。5 次 GET 同内容应保持 2，不应翻到 10。
    """
    counting_storage.load_count = 0
    for _ in range(5):
        r = await client.get(CRL_PATH)
        assert r.status_code == 200
    assert counting_storage.load_count == 2, (
        f"expected 2 (one build), got {counting_storage.load_count} "
        "(cache not engaged — re-signed on every request)"
    )


@pytest.mark.asyncio
async def test_sequence_only_bumps_on_content_change(
    client: httpx.AsyncClient, api_key: str
) -> None:
    """sequence 应当只在内容变更时递增（用 InMemoryRevocationStore 直接观察）。"""
    store = InMemoryRevocationStore()

    # 用纯净的 in-memory CrlManager 绕开 HTTP，专注 sequence 语义
    from app.core.key_storage.local_file.backend import LocalFileKeyStorage
    from pathlib import Path as P
    import tempfile

    tmp = tempfile.TemporaryDirectory()
    storage = LocalFileKeyStorage(root=P(tmp.name), passphrase="x")
    await generate_and_save_signing_key(storage, algorithm="ed25519")
    mgr = CrlManager(store=store, key_storage=storage, algorithm="ed25519")

    hit_a = await mgr.build_crl()
    hit_b = await mgr.build_crl()
    hit_c = await mgr.build_crl()
    assert hit_a.sequence == hit_b.sequence == hit_c.sequence  # 内容相同 → 不递增

    # 改内容 → sequence 必须前进
    await mgr.revoke("lic-1", reason="x")
    hit_d = await mgr.build_crl()
    assert hit_d.sequence > hit_a.sequence

    tmp.cleanup()
