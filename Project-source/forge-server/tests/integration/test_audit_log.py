"""审计日志端到端测试：
- 登录成功 → 写 auth.login.success
- 登录失败（错密码 / 不存在的用户 / 停用账户）→ 写 auth.login.failure + reason
- 登出 → 写 auth.logout
- 签发 license（admin session）→ 写 license.issued + actor=user
- 签发 license（api key）→ 写 license.issued + actor=api_key
- GET /api/v1/audit 需要 admin session
- GET /api/v1/audit 支持 action / actor_id / target_type 过滤
- 审计字段：client_ip, user_agent, request_id 能从请求 header 抽到
- 审计写失败（仓储被替换为抛异常）不影响业务调用
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
    await user_repo.create(
        username="admin",
        email="admin@forge.local",
        plaintext_password="correct-horse-battery-staple",
        is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plaintext = await api_key_repo.issue(customer_id="c", project_label="p")
    audit_repo = AuditLogRepository(db)

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
        audit_log_repository=audit_repo,
    )
    return state, api_plaintext, audit_repo


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
def audit_repo(app_state) -> AuditLogRepository:
    return app_state[2]


# ────────────────────────────────────────────────────────────


async def _login(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )


@pytest.mark.asyncio
async def test_login_success_writes_audit(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository
) -> None:
    r = await _login(client)
    assert r.status_code == 200

    rows = await audit_repo.list(action="auth.login.success")
    assert len(rows) == 1
    assert rows[0].actor_type == "user"
    assert rows[0].target_type == "user"
    assert rows[0].payload["username"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password_writes_audit_with_reason(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository
) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "WRONG"},
    )
    assert r.status_code == 401

    rows = await audit_repo.list(action="auth.login.failure")
    assert len(rows) == 1
    assert rows[0].actor_id == "admin"
    assert rows[0].payload["reason"] == "bad_password"


@pytest.mark.asyncio
async def test_login_unknown_user_writes_audit(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository
) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "anything"},
    )
    assert r.status_code == 401

    rows = await audit_repo.list(action="auth.login.failure")
    assert len(rows) == 1
    assert rows[0].payload["reason"] == "user_missing"


@pytest.mark.asyncio
async def test_login_inactive_user_writes_audit(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository, app_state
) -> None:
    state, _, _ = app_state
    admin = await state.user_repository.get_by_username("admin")
    await state.user_repository.deactivate(admin.id)

    r = await _login(client)
    assert r.status_code == 401

    rows = await audit_repo.list(action="auth.login.failure")
    assert len(rows) == 1
    assert rows[0].payload["reason"] == "inactive"


@pytest.mark.asyncio
async def test_logout_writes_audit(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository
) -> None:
    await _login(client)
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204

    rows = await audit_repo.list(action="auth.logout")
    assert len(rows) == 1
    assert rows[0].actor_type == "user"


@pytest.mark.asyncio
async def test_issue_with_admin_writes_audit_with_user_actor(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository
) -> None:
    await _login(client)
    r = await client.post(
        "/api/v1/licenses/issue",
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    license_id = r.json()["license_id"]

    rows = await audit_repo.list(action="license.issued")
    assert len(rows) == 1
    assert rows[0].actor_type == "user"
    assert rows[0].target_id == license_id
    assert rows[0].payload["customer_id"] == "c"
    assert rows[0].payload["algorithm"] == "ed25519"


@pytest.mark.asyncio
async def test_issue_with_api_key_writes_audit_with_apikey_actor(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository, api_key: str
) -> None:
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

    rows = await audit_repo.list(action="license.issued")
    assert len(rows) == 1
    assert rows[0].actor_type == "api_key"


@pytest.mark.asyncio
async def test_audit_endpoint_requires_admin_session(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/audit")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_audit_endpoint_lists_and_filters(client: httpx.AsyncClient) -> None:
    # 触发若干事件
    await _login(client)
    await client.post(
        "/api/v1/licenses/issue",
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )

    r = await client.get("/api/v1/audit")
    assert r.status_code == 200
    items = r.json()["items"]
    # 至少有 login 和 issue 两条
    actions = {i["action"] for i in items}
    assert "auth.login.success" in actions
    assert "license.issued" in actions

    # 按 action 过滤
    r2 = await client.get("/api/v1/audit", params={"action": "license.issued"})
    assert r2.status_code == 200
    items2 = r2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["action"] == "license.issued"


@pytest.mark.asyncio
async def test_audit_endpoint_pagination(client: httpx.AsyncClient) -> None:
    await _login(client)
    # 触发 3 条 issue
    for _ in range(3):
        await client.post(
            "/api/v1/licenses/issue",
            json={
                "customer_id": "c", "product_id": "p", "mode": "offline",
                "scope": "instance", "algorithm": "ed25519", "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )

    r = await client.get(
        "/api/v1/audit",
        params={"action": "license.issued", "limit": 2, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 2
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_audit_captures_request_metadata(
    client: httpx.AsyncClient, audit_repo: AuditLogRepository
) -> None:
    await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
        headers={
            "User-Agent": "forge-test-agent/1.0",
            "X-Request-ID": "req-xyz-123",
            "X-Forwarded-For": "203.0.113.42, 10.0.0.1",
        },
    )
    rows = await audit_repo.list(action="auth.login.success")
    assert len(rows) == 1
    assert rows[0].request_id == "req-xyz-123"
    assert rows[0].client_ip == "203.0.113.42"  # X-Forwarded-For 取第一个
    assert rows[0].user_agent == "forge-test-agent/1.0"


@pytest.mark.asyncio
async def test_audit_failure_does_not_break_business(
    client: httpx.AsyncClient, app_state
) -> None:
    """审计仓储抛异常时业务调用仍然成功。"""
    state, _, _ = app_state

    class BrokenRepo:
        async def record(self, **_kwargs):
            raise RuntimeError("disk full")

    state.audit_log_repository = BrokenRepo()

    r = await _login(client)
    assert r.status_code == 200, r.text  # 登录仍然成功
