"""Admin Session 登录流端到端测试：
- 注册 admin 用户（用 UserRepository）
- POST /auth/login → 返回 Set-Cookie
- GET /auth/me → 用 cookie 拿到当前 admin
- POST /auth/logout → cookie 清除 + /me 401
- /issue 接受 admin session（不需要 API Key）
- /issue 也接受 API Key（fallback）
- 错密码 → 401 + 不区分错原因
- 关闭 user → 登录失败
- 篡改 session id → 401
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
from app.middleware.admin_session import SESSION_COOKIE_NAME
from app.middleware.api_key_auth import API_KEY_HEADER
from app.models import Base
from app.repositories import (
    ApiKeyRepository,
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
    # 预置一个 admin
    await user_repo.create(
        username="admin",
        email="admin@forge.local",
        plaintext_password="correct-horse-battery-staple",
        is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plaintext = await api_key_repo.issue(customer_id="c", project_label="p")

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
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
    )
    return state, api_plaintext


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
async def test_login_success(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == "admin"
    assert body["is_super"] is True
    # 普通密码（不是文档化默认）→ False
    assert body["is_default_password"] is False
    assert SESSION_COOKIE_NAME in r.cookies


@pytest.mark.asyncio
async def test_login_with_default_password_flags_session(
    client: httpx.AsyncClient, app_state
) -> None:
    """文档化默认密码登录的 admin —— LoginResponse / /me 都要打 is_default_password=True。"""
    state, _ = app_state
    # 单独造一个用户名 = 默认密码的 admin（避免污染其他测试用的 admin）
    default_pw = state.settings.bootstrap_admin_password
    assert default_pw, "settings.bootstrap_admin_password must be set for this test"
    await state.user_repository.create(
        username="docs-default",
        email="docs-default@forge.local",
        plaintext_password=default_pw,
        is_super=False,
    )

    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "docs-default", "password": default_pw},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_default_password"] is True

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["is_default_password"] is True


@pytest.mark.asyncio
async def test_change_password_clears_default_flag(
    client: httpx.AsyncClient, app_state
) -> None:
    """改完密 → session 销毁 → 下次用新密码登 → is_default_password=False。"""
    state, _ = app_state
    default_pw = state.settings.bootstrap_admin_password
    await state.user_repository.create(
        username="docs-default2",
        email="docs-default2@forge.local",
        plaintext_password=default_pw,
        is_super=False,
    )

    # 用默认密码登 → 横幅条件成立
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "docs-default2", "password": default_pw},
    )
    assert r.json()["is_default_password"] is True

    # 改密 → 204 + cookie 清除
    new_pw = "long-enough-new-password-9999"
    rc = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": default_pw, "new_password": new_pw},
    )
    assert rc.status_code == 204
    client.cookies.delete(SESSION_COOKIE_NAME)

    # 用新密码重新登录 → 横幅消失
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"username": "docs-default2", "password": new_pw},
    )
    assert r2.status_code == 200
    assert r2.json()["is_default_password"] is False


@pytest.mark.asyncio
async def test_login_wrong_password(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert r.status_code == 401
    assert SESSION_COOKIE_NAME not in r.cookies
    assert r.json()["detail"] == "invalid credentials"  # 不暴露"用户不存在"vs"密码错"


@pytest.mark.asyncio
async def test_login_unknown_user(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "anything"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_me_requires_session(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_admin_with_session(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_logout_destroys_session(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    # 验证登录中
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204

    # 登出后再调 /me → 401
    me_after = await client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


@pytest.mark.asyncio
async def test_tampered_session_rejected(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    # 篡改 cookie
    client.cookies.set(SESSION_COOKIE_NAME, "totally-fake-session-id")
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_issue_works_with_admin_session(client: httpx.AsyncClient) -> None:
    """登录后调 /issue 不带 API Key 也能签发。"""
    await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    r = await client.post(
        "/api/v1/licenses/issue",
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["issued_by"].startswith("admin:")


@pytest.mark.asyncio
async def test_issue_still_works_with_api_key(client: httpx.AsyncClient, api_key: str) -> None:
    """未登录时用 API Key 仍可签发。"""
    r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["issued_by"].startswith("apikey:")


@pytest.mark.asyncio
async def test_issue_rejects_no_auth(client: httpx.AsyncClient) -> None:
    """既无 session 又无 API Key → 401。"""
    r = await client.post(
        "/api/v1/licenses/issue",
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_deactivated_user_cannot_login(client: httpx.AsyncClient, app_state) -> None:
    state, _ = app_state
    # 先停用 admin
    admin = await state.user_repository.get_by_username("admin")
    await state.user_repository.deactivate(admin.id)

    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 401
