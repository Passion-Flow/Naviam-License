"""API Key 管理端到端测试：
- 三端点都要求 admin session，API Key 不行（防 lateral movement）
- issue → 明文只返回一次；签发后可立刻用于 /licenses/issue
- list → 不返回明文 / 只返回 prefix；支持 status / customer_id 过滤
- revoke → 状态变 revoked；用被吊销的 key 调 /licenses/issue → 401
- revoke 不存在的 key → 404
- revoke 已吊销的 key → 幂等 200，但只写一条审计
- audit：apikey.issued + apikey.revoked 落地
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    # 预置一把现成的 API Key 用来调 negative-control 测试（防止管理端点接受 API Key）
    seed_model, seed_plain = await api_key_repo.issue(customer_id="seed-c", project_label="seed-p")

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
    )
    return state, seed_plain, seed_model.key_id, admin.id


@pytest.fixture
async def client(app_state):
    state, _, _, _ = app_state
    app = create_app(state_builder=lambda: state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


@pytest.fixture
def seed_api_key(app_state) -> str:
    return app_state[1]


@pytest.fixture
def seed_key_id(app_state) -> str:
    return app_state[2]


@pytest.fixture
def admin_id(app_state) -> str:
    return app_state[3]


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200, r.text


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_requires_admin_session(client: httpx.AsyncClient, seed_api_key: str) -> None:
    body = {"customer_id": "acme", "project_label": "main"}
    # 无任何凭证
    r1 = await client.post("/api/v1/api-keys", json=body)
    assert r1.status_code == 401
    # 用 API Key 也不允许（防 lateral movement）
    r2 = await client.post("/api/v1/api-keys", json=body, headers={API_KEY_HEADER: seed_api_key})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_issue_returns_plaintext_once_and_works(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/api-keys",
        json={"customer_id": "acme", "project_label": "main"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["plaintext"]  # 明文返回一次
    assert body["key_prefix"] == body["plaintext"][:8]
    assert body["status"] == "active"

    # 该 key 应该可以立刻调 /licenses/issue
    plaintext = body["plaintext"]
    # 复用 client（带 admin cookie）—— 但 issue 不依赖 cookie，可以直接用 api key
    fresh_client = httpx.AsyncClient(transport=client._transport, base_url="http://t")
    try:
        r2 = await fresh_client.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: plaintext},
            json={
                "customer_id": "acme", "product_id": "p", "mode": "offline",
                "scope": "instance", "algorithm": "ed25519", "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["issued_by"].startswith("apikey:")
    finally:
        await fresh_client.aclose()


@pytest.mark.asyncio
async def test_list_requires_admin_session(client: httpx.AsyncClient, seed_api_key: str) -> None:
    r1 = await client.get("/api/v1/api-keys")
    assert r1.status_code == 401
    r2 = await client.get("/api/v1/api-keys", headers={API_KEY_HEADER: seed_api_key})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_list_returns_metadata_without_plaintext(client: httpx.AsyncClient) -> None:
    await _login(client)
    # seed key 已经存在
    r = await client.get("/api/v1/api-keys")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for it in items:
        assert "plaintext" not in it
        assert "key_hash" not in it
        assert it["key_prefix"]


@pytest.mark.asyncio
async def test_list_filters(client: httpx.AsyncClient) -> None:
    await _login(client)
    # 再签 2 把 active key 给不同客户
    await client.post("/api/v1/api-keys", json={"customer_id": "acme", "project_label": "p1"})
    await client.post("/api/v1/api-keys", json={"customer_id": "globex", "project_label": "p2"})

    r_all = await client.get("/api/v1/api-keys")
    assert len(r_all.json()["items"]) >= 3

    r_acme = await client.get("/api/v1/api-keys", params={"customer_id": "acme"})
    items = r_acme.json()["items"]
    assert all(i["customer_id"] == "acme" for i in items)

    r_active = await client.get("/api/v1/api-keys", params={"status": "active"})
    assert all(i["status"] == "active" for i in r_active.json()["items"])


@pytest.mark.asyncio
async def test_revoke_requires_admin_session(
    client: httpx.AsyncClient, seed_api_key: str, seed_key_id: str
) -> None:
    r1 = await client.post(f"/api/v1/api-keys/{seed_key_id}/revoke")
    assert r1.status_code == 401
    r2 = await client.post(
        f"/api/v1/api-keys/{seed_key_id}/revoke",
        headers={API_KEY_HEADER: seed_api_key},
    )
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_revoke_unknown_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post("/api/v1/api-keys/no-such-id/revoke")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_revoke_disables_key(
    client: httpx.AsyncClient, seed_api_key: str, seed_key_id: str
) -> None:
    await _login(client)
    r = await client.post(f"/api/v1/api-keys/{seed_key_id}/revoke")
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"

    # 用被吊销的 key 调 /licenses/issue → 401
    fresh_client = httpx.AsyncClient(transport=client._transport, base_url="http://t")
    try:
        r2 = await fresh_client.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: seed_api_key},
            json={
                "customer_id": "c", "product_id": "p", "mode": "offline",
                "scope": "instance", "algorithm": "ed25519", "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        assert r2.status_code == 401
    finally:
        await fresh_client.aclose()


@pytest.mark.asyncio
async def test_revoke_is_idempotent(
    client: httpx.AsyncClient, seed_key_id: str, app_state
) -> None:
    state, _, _, _ = app_state
    await _login(client)

    r1 = await client.post(f"/api/v1/api-keys/{seed_key_id}/revoke")
    r2 = await client.post(f"/api/v1/api-keys/{seed_key_id}/revoke")
    assert r1.status_code == 200
    assert r2.status_code == 200

    # 只写一条 apikey.revoked
    rows = await state.audit_log_repository.list(action="apikey.revoked")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_issue_without_ttl_is_never_expires(client: httpx.AsyncClient) -> None:
    """不传 expires_in_days → expires_at 为 null（向后兼容旧客户）。"""
    await _login(client)
    r = await client.post(
        "/api/v1/api-keys",
        json={"customer_id": "acme", "project_label": "no-ttl"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["expires_at"] is None


@pytest.mark.asyncio
async def test_issue_with_ttl_persists_expires_at(client: httpx.AsyncClient) -> None:
    """传 expires_in_days → 响应 + 列表都返回 expires_at。"""
    await _login(client)
    r = await client.post(
        "/api/v1/api-keys",
        json={"customer_id": "acme", "project_label": "with-ttl", "expires_in_days": 30},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["expires_at"] is not None
    exp = datetime.fromisoformat(body["expires_at"])
    delta = exp - datetime.now(timezone.utc)
    # 30 天 ± 1 分钟容差（响应时间 + 时钟漂移）
    assert timedelta(days=30) - timedelta(minutes=1) < delta < timedelta(days=30) + timedelta(minutes=1)

    # 列表里也要带 expires_at
    rl = await client.get("/api/v1/api-keys", params={"customer_id": "acme"})
    items = rl.json()["items"]
    hit = next(i for i in items if i["key_id"] == body["key_id"])
    assert hit["expires_at"] == body["expires_at"]


@pytest.mark.asyncio
async def test_expired_key_is_rejected_at_auth(
    client: httpx.AsyncClient, app_state
) -> None:
    """expires_at 是过去 → /licenses/issue 用该 key → 401（即使 status='active'）。"""
    state, _, _, _ = app_state
    repo = state.api_key_repository
    # 直接造一把已过期 key（绕开 issue 路由的 ge=1 校验）
    _, plaintext = await repo.issue(
        customer_id="acme",
        project_label="expired",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://t")
    try:
        r = await fresh.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: plaintext},
            json={
                "customer_id": "acme", "product_id": "p", "mode": "offline",
                "scope": "instance", "algorithm": "ed25519", "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        assert r.status_code == 401
    finally:
        await fresh.aclose()


@pytest.mark.asyncio
async def test_expires_in_days_out_of_range_rejected(client: httpx.AsyncClient) -> None:
    """expires_in_days <= 0 或 > 10 年 → 422（pydantic 拒绝）。"""
    await _login(client)
    for bad in (0, -1, 365 * 10 + 1):
        r = await client.post(
            "/api/v1/api-keys",
            json={"customer_id": "acme", "project_label": "bad-ttl", "expires_in_days": bad},
        )
        assert r.status_code == 422, (bad, r.text)


@pytest.mark.asyncio
async def test_audit_records_for_issue_and_revoke(
    client: httpx.AsyncClient, admin_id: str, app_state
) -> None:
    state, _, _, _ = app_state
    await _login(client)

    issued = await client.post(
        "/api/v1/api-keys",
        json={"customer_id": "acme", "project_label": "main"},
    )
    new_key_id = issued.json()["key_id"]

    await client.post(f"/api/v1/api-keys/{new_key_id}/revoke")

    issued_rows = await state.audit_log_repository.list(action="apikey.issued")
    revoked_rows = await state.audit_log_repository.list(action="apikey.revoked")
    assert any(r.target_id == new_key_id and r.actor_id == admin_id for r in issued_rows)
    assert any(r.target_id == new_key_id and r.actor_id == admin_id for r in revoked_rows)
    # 签发审计应含 prefix（便于追溯）
    issued_for_new = [r for r in issued_rows if r.target_id == new_key_id][0]
    assert issued_for_new.payload["key_prefix"]
    assert issued_for_new.payload["customer_id"] == "acme"
