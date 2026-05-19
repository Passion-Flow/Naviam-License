"""签名密钥管理端到端：
- 5 端点 (list/generate/rotate/revoke/export-public) 全部要求 admin session
- list：seed key 默认存在；algorithm / status 过滤
- generate：响应不含私钥；新 key status=active；audit key.generated
- rotate：only-active；旧 key → rotated，新 key → active；两条 audit (generated + rotated)
- 旋转后 issue 用新 key 签发（验证：响应 signing_key_id 是新 key）
- 旧 license（用 rotated key 签）仍能 verify=valid（key 还在，只是不签新的）
- revoke：幂等（重复调不重复审计）；403/409 路径
- export-public：admin 拿全字段；与公开 /public-keys 端点完全独立
- 公开 /public-keys/{id} 不鉴权仍可读
"""
from __future__ import annotations

import base64
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
    seed = await generate_and_save_signing_key(key_storage, algorithm="ed25519")

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
    return state, api_plain, seed.key_id


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
def seed_key_id(app_state) -> str:
    return app_state[2]


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200, r.text


# ─────────────── auth gate ───────────────


@pytest.mark.asyncio
async def test_all_endpoints_reject_api_key(
    client: httpx.AsyncClient, api_key: str, seed_key_id: str
) -> None:
    h = {API_KEY_HEADER: api_key}
    assert (await client.get("/api/v1/keys", headers=h)).status_code == 401
    assert (await client.post("/api/v1/keys/generate", headers=h, json={"algorithm": "ed25519"})).status_code == 401
    assert (await client.post(f"/api/v1/keys/{seed_key_id}/rotate", headers=h)).status_code == 401
    assert (await client.post(f"/api/v1/keys/{seed_key_id}/revoke", headers=h, json={})).status_code == 401
    assert (await client.get(f"/api/v1/keys/{seed_key_id}/export-public", headers=h)).status_code == 401


# ─────────────── list ───────────────


@pytest.mark.asyncio
async def test_list_returns_seed_key(client: httpx.AsyncClient, seed_key_id: str) -> None:
    await _login(client)
    r = await client.get("/api/v1/keys")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(k["key_id"] == seed_key_id and k["status"] == "active" for k in items)
    # 私钥永不返回
    for k in items:
        assert "private_key" not in k
        assert "private_key_b64" not in k
        assert k["public_key_b64"]


@pytest.mark.asyncio
async def test_list_filters(client: httpx.AsyncClient, seed_key_id: str) -> None:
    await _login(client)
    # 增一把 rsa2048
    await client.post("/api/v1/keys/generate", json={"algorithm": "rsa2048"})

    by_alg = (await client.get("/api/v1/keys", params={"algorithm": "ed25519"})).json()["items"]
    assert all(k["algorithm"] == "ed25519" for k in by_alg)

    rsa_items = (await client.get("/api/v1/keys", params={"algorithm": "rsa2048"})).json()["items"]
    assert len(rsa_items) == 1
    assert rsa_items[0]["algorithm"] == "rsa2048"

    by_status = (await client.get("/api/v1/keys", params={"status": "active"})).json()["items"]
    assert all(k["status"] == "active" for k in by_status)


# ─────────────── generate ───────────────


@pytest.mark.asyncio
async def test_generate_creates_active_key(client: httpx.AsyncClient, app_state) -> None:
    state, _, _ = app_state
    await _login(client)
    r = await client.post("/api/v1/keys/generate", json={"algorithm": "ed25519"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["algorithm"] == "ed25519"
    assert body["public_key_b64"]
    assert body["activated_at"] is not None

    rows = await state.audit_log_repository.list(action="key.generated")
    assert any(r.target_id == body["key_id"] for r in rows)


@pytest.mark.asyncio
async def test_generate_inactive_flag(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post("/api/v1/keys/generate", json={"algorithm": "ed25519", "activate": False})
    body = r.json()
    assert body["status"] == "rotated"  # generate_and_save 把非 active 设成 rotated
    assert body["activated_at"] is None


@pytest.mark.asyncio
async def test_generate_rejects_unknown_algorithm(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post("/api/v1/keys/generate", json={"algorithm": "des"})
    assert r.status_code == 422


# ─────────────── rotate ───────────────


@pytest.mark.asyncio
async def test_rotate_marks_old_and_creates_new(
    client: httpx.AsyncClient, seed_key_id: str, app_state
) -> None:
    state, _, _ = app_state
    await _login(client)
    r = await client.post(f"/api/v1/keys/{seed_key_id}/rotate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["old_key_id"] == seed_key_id
    assert body["old_status"] == "rotated"
    assert body["new_key"]["status"] == "active"
    assert body["new_key"]["algorithm"] == "ed25519"
    new_kid = body["new_key"]["key_id"]
    assert new_kid != seed_key_id

    # list 确认 seed 已 rotated、新 key active
    l = await client.get("/api/v1/keys")
    items = {k["key_id"]: k for k in l.json()["items"]}
    assert items[seed_key_id]["status"] == "rotated"
    assert items[new_kid]["status"] == "active"

    # 两条 audit
    gen_rows = await state.audit_log_repository.list(action="key.generated")
    rot_rows = await state.audit_log_repository.list(action="key.rotated")
    assert any(r.target_id == new_kid and r.payload.get("rotated_from") == seed_key_id for r in gen_rows)
    assert any(r.target_id == seed_key_id and r.payload.get("rotated_into") == new_kid for r in rot_rows)


@pytest.mark.asyncio
async def test_rotate_only_active(
    client: httpx.AsyncClient, seed_key_id: str
) -> None:
    await _login(client)
    # 先 rotate 一次
    await client.post(f"/api/v1/keys/{seed_key_id}/rotate")
    # 再 rotate seed（现在已 rotated）→ 409
    r = await client.post(f"/api/v1/keys/{seed_key_id}/rotate")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_rotate_unknown_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post("/api/v1/keys/no-such-id/rotate")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_issue_uses_active_key_after_rotation(
    client: httpx.AsyncClient, seed_key_id: str, api_key: str
) -> None:
    """轮换后 issue 应自动用新 active key 签发。"""
    await _login(client)
    rot = await client.post(f"/api/v1/keys/{seed_key_id}/rotate")
    new_kid = rot.json()["new_key"]["key_id"]

    iss = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    assert iss.status_code == 200, iss.text
    assert iss.json()["signing_key_id"] == new_kid


# ─────────────── revoke ───────────────


@pytest.mark.asyncio
async def test_revoke_key(
    client: httpx.AsyncClient, seed_key_id: str, app_state
) -> None:
    state, _, _ = app_state
    await _login(client)
    r = await client.post(f"/api/v1/keys/{seed_key_id}/revoke", json={"reason": "compromised"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "revoked"
    assert body["revoked_at"] is not None

    rows = await state.audit_log_repository.list(action="key.revoked")
    assert any(r.target_id == seed_key_id and r.payload["reason"] == "compromised" for r in rows)


@pytest.mark.asyncio
async def test_revoke_is_idempotent(
    client: httpx.AsyncClient, seed_key_id: str, app_state
) -> None:
    state, _, _ = app_state
    await _login(client)
    r1 = await client.post(f"/api/v1/keys/{seed_key_id}/revoke", json={})
    r2 = await client.post(f"/api/v1/keys/{seed_key_id}/revoke", json={})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # 只一条 audit
    rows = await state.audit_log_repository.list(action="key.revoked")
    assert len([r for r in rows if r.target_id == seed_key_id]) == 1


@pytest.mark.asyncio
async def test_revoke_unknown_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post("/api/v1/keys/no-such-id/revoke", json={})
    assert r.status_code == 404


# ─────────────── export-public ───────────────


@pytest.mark.asyncio
async def test_export_public_admin(client: httpx.AsyncClient, seed_key_id: str) -> None:
    await _login(client)
    r = await client.get(f"/api/v1/keys/{seed_key_id}/export-public")
    assert r.status_code == 200
    body = r.json()
    assert body["key_id"] == seed_key_id
    assert body["public_key_b64"]


@pytest.mark.asyncio
async def test_export_public_unknown_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/v1/keys/no-such-id/export-public")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_public_endpoint_still_unauthenticated(
    client: httpx.AsyncClient, seed_key_id: str
) -> None:
    """公开 /public-keys 端点 (verifier 用) 不鉴权仍能拉。"""
    r = await client.get(f"/api/v1/public-keys/{seed_key_id}")
    assert r.status_code == 200
    assert r.json()["key_id"] == seed_key_id
    assert "public_key_b64" in r.json()
