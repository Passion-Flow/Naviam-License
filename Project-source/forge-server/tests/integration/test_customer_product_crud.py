"""Customer / Product CRUD 端到端测试：
- 全 9 端点都要求 admin session（API Key 一律拒）
- create：slug 冲突 → 409；slug 不可后续修改
- list：默认全量 / status 过滤 / 分页
- detail：404 / 200
- update：空 body 直接返回；status 改 archived → list 默认仍含（除非加 filter）
- customer delete：软归档 status=archived，不真正删
- audit：5 个动作落地（customer.created/updated/archived + product.created/updated）
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
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.middleware.api_key_auth import API_KEY_HEADER
from app.models import Base
from app.repositories import (
    ApiKeyRepository,
    AuditLogRepository,
    CustomerRepository,
    DbBackedApiKeyAuth,
    DbBackedRevocationStore,
    LicenseRepository,
    ProductRepository,
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
    await generate_and_save_signing_key(key_storage, algorithm="ed25519")

    revocation_store = DbBackedRevocationStore(db)
    user_repo = UserRepository(db)
    admin = await user_repo.create(
        username="admin",
        email="admin@forge.local",
        plaintext_password="correct-horse-battery-staple",
        is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plain = await api_key_repo.issue(customer_id="seed", project_label="seed")

    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=revocation_store,
        crl_manager=CrlManager(store=revocation_store, key_storage=key_storage, algorithm="ed25519"),
        heartbeat_collector=InMemoryHeartbeatCollector(),
        multi_env_detector=MultiEnvDetector(window=timedelta(hours=24), threshold=1),
        api_keys={},
        database=db,
        license_repository=LicenseRepository(db),
        api_key_auth=DbBackedApiKeyAuth(api_key_repo),
        api_key_repository=api_key_repo,
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
        audit_log_repository=AuditLogRepository(db),
        customer_repository=CustomerRepository(db),
        product_repository=ProductRepository(db),
    )
    return state, api_plain, admin.id


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
def admin_id(app_state) -> str:
    return app_state[2]


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200, r.text


# ─────────────── Customer ───────────────


@pytest.mark.asyncio
async def test_customer_endpoints_reject_api_key(client: httpx.AsyncClient, api_key: str) -> None:
    h = {API_KEY_HEADER: api_key}
    # 5 端点都得 401
    assert (await client.post("/api/v1/customers", json={"slug": "x", "name": "x"}, headers=h)).status_code == 401
    assert (await client.get("/api/v1/customers", headers=h)).status_code == 401
    assert (await client.get("/api/v1/customers/abc", headers=h)).status_code == 401
    assert (await client.patch("/api/v1/customers/abc", json={"name": "y"}, headers=h)).status_code == 401
    assert (await client.delete("/api/v1/customers/abc", headers=h)).status_code == 401


@pytest.mark.asyncio
async def test_customer_create_and_detail(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/customers",
        json={
            "slug": "acme",
            "name": "Acme Inc.",
            "contact_email": "ops@acme.test",
            "region": "us-east",
            "notes": "key account",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "acme"
    assert body["status"] == "active"
    cid = body["id"]

    r2 = await client.get(f"/api/v1/customers/{cid}")
    assert r2.status_code == 200
    assert r2.json()["contact_email"] == "ops@acme.test"


@pytest.mark.asyncio
async def test_customer_create_slug_conflict(client: httpx.AsyncClient) -> None:
    await _login(client)
    await client.post("/api/v1/customers", json={"slug": "acme", "name": "Acme"})
    r = await client.post("/api/v1/customers", json={"slug": "acme", "name": "Acme Again"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_customer_list_and_filter(client: httpx.AsyncClient) -> None:
    await _login(client)
    await client.post("/api/v1/customers", json={"slug": "a", "name": "A"})
    b = (await client.post("/api/v1/customers", json={"slug": "b", "name": "B"})).json()
    await client.patch(f"/api/v1/customers/{b['id']}", json={"status": "archived"})

    all_items = (await client.get("/api/v1/customers")).json()["items"]
    assert len(all_items) >= 2
    active = (await client.get("/api/v1/customers", params={"status": "active"})).json()["items"]
    assert all(i["status"] == "active" for i in active)
    archived = (await client.get("/api/v1/customers", params={"status": "archived"})).json()["items"]
    assert len(archived) >= 1


@pytest.mark.asyncio
async def test_customer_update_rejects_slug_and_unknown_fields(client: httpx.AsyncClient) -> None:
    await _login(client)
    c = (await client.post("/api/v1/customers", json={"slug": "x", "name": "X"})).json()
    # Pydantic extra=forbid 应当拒掉 slug
    r = await client.patch(f"/api/v1/customers/{c['id']}", json={"slug": "renamed"})
    assert r.status_code == 422
    # name 修改成功
    r2 = await client.patch(f"/api/v1/customers/{c['id']}", json={"name": "X v2"})
    assert r2.status_code == 200
    assert r2.json()["name"] == "X v2"
    assert r2.json()["slug"] == "x"


@pytest.mark.asyncio
async def test_customer_delete_is_soft_archive(client: httpx.AsyncClient) -> None:
    await _login(client)
    c = (await client.post("/api/v1/customers", json={"slug": "x", "name": "X"})).json()
    r = await client.delete(f"/api/v1/customers/{c['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"
    # detail 仍能查得到（软删）
    r2 = await client.get(f"/api/v1/customers/{c['id']}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_customer_detail_unknown_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/v1/customers/no-such-id")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_customer_audit_events_recorded(
    client: httpx.AsyncClient, admin_id: str, app_state
) -> None:
    state, _, _ = app_state
    await _login(client)
    c = (await client.post("/api/v1/customers", json={"slug": "auditx", "name": "X"})).json()
    await client.patch(f"/api/v1/customers/{c['id']}", json={"name": "X v2"})
    await client.delete(f"/api/v1/customers/{c['id']}")

    repo = state.audit_log_repository
    created = await repo.list(action="customer.created")
    updated = await repo.list(action="customer.updated")
    archived = await repo.list(action="customer.archived")
    assert any(r.target_id == c["id"] and r.actor_id == admin_id for r in created)
    assert any(r.target_id == c["id"] and "name" in r.payload["updated_fields"] for r in updated)
    assert any(r.target_id == c["id"] and r.payload["slug"] == "auditx" for r in archived)


# ─────────────── Product ───────────────


@pytest.mark.asyncio
async def test_product_endpoints_reject_api_key(client: httpx.AsyncClient, api_key: str) -> None:
    h = {API_KEY_HEADER: api_key}
    assert (await client.post("/api/v1/products", json={"slug": "x", "name": "X"}, headers=h)).status_code == 401
    assert (await client.get("/api/v1/products", headers=h)).status_code == 401
    assert (await client.get("/api/v1/products/abc", headers=h)).status_code == 401
    assert (await client.patch("/api/v1/products/abc", json={"name": "y"}, headers=h)).status_code == 401


@pytest.mark.asyncio
async def test_product_create_with_schema(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/products",
        json={
            "slug": "naviam",
            "name": "Naviam",
            "version": "1.0.0",
            "features_schema": {"hd_video": "bool", "max_users": "int"},
            "default_limits": {"max_users": 100},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["features_schema"] == {"hd_video": "bool", "max_users": "int"}
    assert body["default_limits"] == {"max_users": 100}


@pytest.mark.asyncio
async def test_product_slug_conflict(client: httpx.AsyncClient) -> None:
    await _login(client)
    await client.post("/api/v1/products", json={"slug": "p", "name": "P"})
    r = await client.post("/api/v1/products", json={"slug": "p", "name": "P-2"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_product_update_fields(client: httpx.AsyncClient) -> None:
    await _login(client)
    p = (await client.post("/api/v1/products", json={"slug": "p1", "name": "P1"})).json()
    r = await client.patch(
        f"/api/v1/products/{p['id']}",
        json={"version": "1.2.0", "default_limits": {"max_users": 200}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1.2.0"
    assert body["default_limits"]["max_users"] == 200


@pytest.mark.asyncio
async def test_product_audit_events_recorded(
    client: httpx.AsyncClient, admin_id: str, app_state
) -> None:
    state, _, _ = app_state
    await _login(client)
    p = (await client.post("/api/v1/products", json={"slug": "audp", "name": "P"})).json()
    await client.patch(f"/api/v1/products/{p['id']}", json={"version": "9"})

    repo = state.audit_log_repository
    created = await repo.list(action="product.created")
    updated = await repo.list(action="product.updated")
    assert any(r.target_id == p["id"] and r.actor_id == admin_id for r in created)
    assert any(r.target_id == p["id"] for r in updated)


@pytest.mark.asyncio
async def test_product_detail_unknown_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/v1/products/no-such-id")
    assert r.status_code == 404
