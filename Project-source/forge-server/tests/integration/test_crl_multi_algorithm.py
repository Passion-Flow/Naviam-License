"""多算法 CRL 端到端：
- enabled list 含 [ed25519, rsa2048, sm2] 时三条路径均 200
- 不在 enabled list 的算法 → 404（即使 ed25519 key 存在也不放行 rsa4096.crl）
- 各算法 CRL 用各自的 active key 签
- 同一 license 吊销后 → 所有算法的 CRL 都失效重建（缓存联动）
- 同算法多次 GET 内容稳定（每算法各自缓存）
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
from app.core.auth import SessionStore
from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import CrlManager
from app.core.license.crl.format import unpack_crl
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
        # 关键：开启 3 个算法
        "SIGNING_ALGORITHMS_ENABLED": '["ed25519","rsa2048","sm2"]',
        "SIGNING_DEFAULT_ALGORITHM": "ed25519",
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


@pytest.fixture
async def app_state(settings, db, cache, tmp_path: Path):
    key_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )
    # 为 3 种算法各生成一把 active key
    await generate_and_save_signing_key(key_storage, algorithm="ed25519")
    await generate_and_save_signing_key(key_storage, algorithm="rsa2048")
    await generate_and_save_signing_key(key_storage, algorithm="sm2")

    revocation_store = DbBackedRevocationStore(db)
    user_repo = UserRepository(db)
    await user_repo.create(
        username="admin", email="admin@forge.local",
        plaintext_password="x", is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plain = await api_key_repo.issue(customer_id="c", project_label="p")

    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=revocation_store,
        crl_manager=CrlManager(
            store=revocation_store,
            key_storage=key_storage,
            algorithm="ed25519",  # 默认，但 build_crl(algorithm=) 可以请求其他算法
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
    return state, api_plain


@pytest.fixture
async def client(app_state):
    state, _ = app_state
    app = create_app(state_builder=lambda: state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


@pytest.fixture
def api_key(app_state) -> str:
    return app_state[1]


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_enabled_algorithms_return_200(client: httpx.AsyncClient) -> None:
    for algo in ["ed25519", "rsa2048", "sm2"]:
        r = await client.get(f"/api/v1/revocation-list/{algo}.crl")
        assert r.status_code == 200, f"{algo} failed: {r.status_code}"
        assert r.headers["Content-Disposition"].endswith(f'forge-{algo}.crl"')


@pytest.mark.asyncio
async def test_disabled_algorithm_returns_404(client: httpx.AsyncClient) -> None:
    # rsa4096 不在 enabled list（即使代码支持）
    r = await client.get("/api/v1/revocation-list/rsa4096.crl")
    assert r.status_code == 404
    # 完全无效算法名也 404
    r2 = await client.get("/api/v1/revocation-list/des.crl")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_each_algorithm_signs_with_its_own_key(client: httpx.AsyncClient) -> None:
    """从 .forge tar 解出 metadata.json，验证 algorithm 与请求路径对应。"""
    for algo in ["ed25519", "rsa2048", "sm2"]:
        r = await client.get(f"/api/v1/revocation-list/{algo}.crl")
        crl = unpack_crl(r.content)
        assert crl.metadata.algorithm == algo


@pytest.mark.asyncio
async def test_etags_differ_across_algorithms(client: httpx.AsyncClient) -> None:
    """同样的吊销集，不同算法的 CRL ETag 不同（algorithm 参与 hash）。"""
    etags = set()
    for algo in ["ed25519", "rsa2048", "sm2"]:
        r = await client.get(f"/api/v1/revocation-list/{algo}.crl")
        etags.add(r.headers["ETag"])
    assert len(etags) == 3


@pytest.mark.asyncio
async def test_revoke_invalidates_all_algorithms_caches(
    client: httpx.AsyncClient, api_key: str
) -> None:
    """单次 revoke 应让三种算法的 CRL ETag 全部前进。"""
    before = {}
    for algo in ["ed25519", "rsa2048", "sm2"]:
        r = await client.get(f"/api/v1/revocation-list/{algo}.crl")
        before[algo] = r.headers["ETag"]

    # 签一份 + 吊销
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
        json={"reason": "x"},
    )

    for algo in ["ed25519", "rsa2048", "sm2"]:
        r = await client.get(f"/api/v1/revocation-list/{algo}.crl")
        assert r.headers["ETag"] != before[algo], f"{algo} ETag did not advance"


@pytest.mark.asyncio
async def test_per_algorithm_independent_caching(client: httpx.AsyncClient) -> None:
    """对 ed25519 多次 GET 应稳定（缓存命中），不会被 rsa2048 的拉取影响。"""
    e1 = (await client.get("/api/v1/revocation-list/ed25519.crl")).headers["ETag"]
    _ = await client.get("/api/v1/revocation-list/rsa2048.crl")
    _ = await client.get("/api/v1/revocation-list/sm2.crl")
    e2 = (await client.get("/api/v1/revocation-list/ed25519.crl")).headers["ETag"]
    assert e1 == e2


@pytest.mark.asyncio
async def test_if_none_match_works_per_algorithm(client: httpx.AsyncClient) -> None:
    """If-None-Match 在每个算法独立工作 —— ed25519 的 ETag 不会让 rsa2048 误判 304。"""
    r_ed = await client.get("/api/v1/revocation-list/ed25519.crl")
    etag_ed = r_ed.headers["ETag"]

    # 把 ed25519 ETag 拿去 rsa2048 探测，必须 200（不匹配）
    r_rsa = await client.get(
        "/api/v1/revocation-list/rsa2048.crl",
        headers={"If-None-Match": etag_ed},
    )
    assert r_rsa.status_code == 200

    # 用 rsa2048 自己的 ETag → 304
    etag_rsa = r_rsa.headers["ETag"]
    r_rsa_again = await client.get(
        "/api/v1/revocation-list/rsa2048.crl",
        headers={"If-None-Match": etag_rsa},
    )
    assert r_rsa_again.status_code == 304
