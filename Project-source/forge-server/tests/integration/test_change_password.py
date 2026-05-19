"""POST /api/v1/auth/change-password 端到端：
- 未登录 → 401
- 当前密码错 → 401
- 新密码 < 12 字符 → 422（pydantic min_length）
- 新旧同密 → 400
- 成功 → 204 + 删 cookie + 老密码失效 + 新密码可登录 + 审计落地
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
from app.core.auth.rate_limit import LoginRateLimiter
from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import CrlManager
from app.core.license.crl.manager import InMemoryRevocationStore
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.middleware.admin_session import SESSION_COOKIE_NAME
from app.models import Base
from app.repositories import AuditLogRepository, UserRepository
from app.settings import Settings
from app.state import AppState


CURRENT = "correct-horse-battery-staple"


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
    user_repo = UserRepository(db)
    await user_repo.create(
        username="admin", email="admin@forge.local",
        plaintext_password=CURRENT, is_super=True,
    )
    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=InMemoryRevocationStore(),
        crl_manager=CrlManager(
            store=InMemoryRevocationStore(),
            key_storage=key_storage,
            algorithm="ed25519",
        ),
        heartbeat_collector=InMemoryHeartbeatCollector(),
        multi_env_detector=MultiEnvDetector(window=timedelta(hours=24), threshold=1),
        api_keys={},
        database=db,
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
        audit_log_repository=AuditLogRepository(db),
        login_rate_limiter=LoginRateLimiter(cache, threshold=5, window_seconds=300),
    )
    return state


@pytest.fixture
async def client(app_state):
    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


async def _login(client: httpx.AsyncClient, *, password: str = CURRENT) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": password},
    )
    assert r.status_code == 200, r.text


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_change_password_requires_login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": CURRENT, "new_password": "new-password-strong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_current_password_rejected(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "WRONG", "new_password": "new-password-strong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_short_new_password_rejected(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": CURRENT, "new_password": "short"},
    )
    # pydantic min_length=12 → 422
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_same_old_new_password_rejected(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": CURRENT, "new_password": CURRENT},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_success_204_and_cookie_cleared(client: httpx.AsyncClient) -> None:
    await _login(client)
    assert SESSION_COOKIE_NAME in client.cookies

    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": CURRENT, "new_password": "brand-new-password-123"},
    )
    assert r.status_code == 204
    # 服务端 delete_cookie 让 httpx 自动清掉本地 cookie jar
    assert SESSION_COOKIE_NAME not in client.cookies

    # /me 应当 401（session 已销毁）
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_old_password_no_longer_works(client: httpx.AsyncClient) -> None:
    await _login(client)
    await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": CURRENT, "new_password": "brand-new-password-123"},
    )
    # 老密码登录失败
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": CURRENT},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_new_password_works(client: httpx.AsyncClient) -> None:
    await _login(client)
    await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": CURRENT, "new_password": "brand-new-password-123"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "brand-new-password-123"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_audit_event_recorded(client: httpx.AsyncClient, app_state) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": CURRENT, "new_password": "brand-new-password-123"},
    )
    assert r.status_code == 204

    rows = await app_state.audit_log_repository.list(action="auth.password.changed")
    assert len(rows) == 1
    assert rows[0].actor_type == "user"
    assert rows[0].payload["username"] == "admin"
    # new password value must never appear in audit payload
    payload_dump = str(rows[0].payload)
    assert "brand-new-password-123" not in payload_dump
