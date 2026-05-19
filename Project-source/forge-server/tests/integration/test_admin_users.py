"""admin/users 端到端：
- list: admin session 即可（含 non-super）
- create: super-only，非 super 403；username/email 冲突 409；短密码 422；password 不进 audit
- deactivate: super-only，不能 deactivate 自己 400；停用后该用户不能登
- reactivate: 把停用账号恢复，该用户重新可登
- reset-password: super-only，不能 reset 自己 400；目标用户新密码生效，老密码失效；payload 不含明文
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
from app.core.license.crl.manager import InMemoryRevocationStore
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.models import Base
from app.repositories import AuditLogRepository, UserRepository
from app.settings import Settings
from app.state import AppState


SUPER_PW = "super-default-password-1"
REGULAR_PW = "regular-default-password-1"


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
        username="root", email="root@forge.local",
        plaintext_password=SUPER_PW, is_super=True,
    )
    await user_repo.create(
        username="alice", email="alice@forge.local",
        plaintext_password=REGULAR_PW, is_super=False,
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
    )
    return state


@pytest.fixture
async def client_super(app_state):
    """已用 super 登录的 client。"""
    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post("/api/v1/auth/login", json={"username": "root", "password": SUPER_PW})
        assert r.status_code == 200
        yield ac


@pytest.fixture
async def client_regular(app_state):
    """已用普通 admin 登录的 client。"""
    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.post("/api/v1/auth/login", json={"username": "alice", "password": REGULAR_PW})
        assert r.status_code == 200
        yield ac


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_visible_to_any_admin(
    client_super: httpx.AsyncClient, client_regular: httpx.AsyncClient
) -> None:
    """非 super admin 也能查看 admin 列表（只读，便于团队认人）。"""
    for ac in (client_super, client_regular):
        r = await ac.get("/api/v1/admin/users")
        assert r.status_code == 200
        usernames = {u["username"] for u in r.json()["items"]}
        assert usernames == {"root", "alice"}


@pytest.mark.asyncio
async def test_create_requires_super(client_regular: httpx.AsyncClient) -> None:
    r = await client_regular.post(
        "/api/v1/admin/users",
        json={
            "username": "bob", "email": "bob@forge.local",
            "password": "bob-strong-password-1",
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_then_login(
    client_super: httpx.AsyncClient, app_state
) -> None:
    r = await client_super.post(
        "/api/v1/admin/users",
        json={
            "username": "bob", "email": "bob@forge.local",
            "password": "bob-strong-password-1",
        },
    )
    assert r.status_code == 201
    assert r.json()["is_super"] is False

    # 新建账号用新密码可以登录
    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": "bob-strong-password-1"},
        )
        assert login.status_code == 200


@pytest.mark.asyncio
async def test_create_username_conflict(client_super: httpx.AsyncClient) -> None:
    r = await client_super.post(
        "/api/v1/admin/users",
        json={
            "username": "alice", "email": "new@forge.local",
            "password": "strong-password-12",
        },
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_email_conflict(client_super: httpx.AsyncClient) -> None:
    r = await client_super.post(
        "/api/v1/admin/users",
        json={
            "username": "new-bob", "email": "alice@forge.local",
            "password": "strong-password-12",
        },
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_short_password_rejected(client_super: httpx.AsyncClient) -> None:
    r = await client_super.post(
        "/api/v1/admin/users",
        json={"username": "x", "email": "x@forge.local", "password": "short"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_audit_no_password_leak(
    client_super: httpx.AsyncClient, app_state
) -> None:
    secret_pw = "ultra-secret-12345"
    await client_super.post(
        "/api/v1/admin/users",
        json={"username": "leak-check", "email": "leak@forge.local", "password": secret_pw},
    )
    rows = await app_state.audit_log_repository.list(action="admin.user.created")
    assert len(rows) == 1
    payload_dump = str(rows[0].payload)
    assert secret_pw not in payload_dump


@pytest.mark.asyncio
async def test_deactivate_requires_super(client_regular: httpx.AsyncClient, app_state) -> None:
    alice = await app_state.user_repository.get_by_username("alice")
    r = await client_regular.post(f"/api/v1/admin/users/{alice.id}/deactivate")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_deactivate_self_rejected(client_super: httpx.AsyncClient, app_state) -> None:
    root = await app_state.user_repository.get_by_username("root")
    r = await client_super.post(f"/api/v1/admin/users/{root.id}/deactivate")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_deactivate_blocks_login(
    client_super: httpx.AsyncClient, app_state
) -> None:
    alice = await app_state.user_repository.get_by_username("alice")
    r = await client_super.post(f"/api/v1/admin/users/{alice.id}/deactivate")
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # alice 不能再登
    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": REGULAR_PW},
        )
        assert login.status_code == 401


@pytest.mark.asyncio
async def test_reactivate_restores_login(
    client_super: httpx.AsyncClient, app_state
) -> None:
    alice = await app_state.user_repository.get_by_username("alice")
    await client_super.post(f"/api/v1/admin/users/{alice.id}/deactivate")
    r = await client_super.post(f"/api/v1/admin/users/{alice.id}/reactivate")
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": REGULAR_PW},
        )
        assert login.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_self_rejected(
    client_super: httpx.AsyncClient, app_state
) -> None:
    root = await app_state.user_repository.get_by_username("root")
    r = await client_super.post(
        f"/api/v1/admin/users/{root.id}/reset-password",
        json={"new_password": "new-strong-password-1"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_changes_target(
    client_super: httpx.AsyncClient, app_state
) -> None:
    alice = await app_state.user_repository.get_by_username("alice")
    new_pw = "alice-new-password-12"
    r = await client_super.post(
        f"/api/v1/admin/users/{alice.id}/reset-password",
        json={"new_password": new_pw},
    )
    assert r.status_code == 200

    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        # 老密码失效
        r_old = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": REGULAR_PW},
        )
        assert r_old.status_code == 401
        # 新密码生效
        r_new = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": new_pw},
        )
        assert r_new.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_audit_no_leak(
    client_super: httpx.AsyncClient, app_state
) -> None:
    alice = await app_state.user_repository.get_by_username("alice")
    new_pw = "another-secret-67890"
    await client_super.post(
        f"/api/v1/admin/users/{alice.id}/reset-password",
        json={"new_password": new_pw},
    )
    rows = await app_state.audit_log_repository.list(action="admin.user.password_reset")
    assert len(rows) == 1
    assert new_pw not in str(rows[0].payload)
