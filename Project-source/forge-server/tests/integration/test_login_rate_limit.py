"""/auth/login 限流端到端：
- 累计失败到 threshold → 429 + Retry-After
- 成功登录清掉计数（再失败 ≥ threshold - 1 次不会立刻 429）
- 限流按 (ip, username) 分桶：同一 username 换 IP 不互相影响
- 已限流后即使密码正确也直接 429（因为早拦截在 check 阶段）
- 限流器为 None 时退化无限流
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
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.models import Base
from app.repositories import UserRepository
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


# Threshold deliberately low — 3 to keep tests snappy.
RL_THRESHOLD = 3


@pytest.fixture
async def app_state(settings, db, cache, tmp_path: Path):
    key_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )
    await generate_and_save_signing_key(key_storage, algorithm="ed25519")
    user_repo = UserRepository(db)
    await user_repo.create(
        username="admin",
        email="admin@forge.local",
        plaintext_password="correct-horse-battery-staple",
        is_super=True,
    )
    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=None,  # type: ignore[arg-type]
        crl_manager=CrlManager(
            store=None,  # type: ignore[arg-type]
            key_storage=key_storage,
            algorithm="ed25519",
        ),
        heartbeat_collector=InMemoryHeartbeatCollector(),
        multi_env_detector=MultiEnvDetector(window=timedelta(hours=24), threshold=1),
        api_keys={},
        database=db,
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
        login_rate_limiter=LoginRateLimiter(cache, threshold=RL_THRESHOLD, window_seconds=300),
    )
    return state


@pytest.fixture
async def client(app_state):
    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


async def _bad_login(client: httpx.AsyncClient, *, username: str = "admin", ip: str = "1.1.1.1") -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "WRONG"},
        headers={"X-Forwarded-For": ip},
    )


async def _good_login(client: httpx.AsyncClient, *, ip: str = "1.1.1.1") -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
        headers={"X-Forwarded-For": ip},
    )


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_failures_return_401(client: httpx.AsyncClient) -> None:
    for _ in range(RL_THRESHOLD - 1):
        r = await _bad_login(client)
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_threshold_failure_returns_429_with_retry_after(client: httpx.AsyncClient) -> None:
    last: httpx.Response | None = None
    for _ in range(RL_THRESHOLD):
        last = await _bad_login(client)
    assert last is not None
    assert last.status_code == 429
    assert int(last.headers.get("Retry-After", "0")) > 0


@pytest.mark.asyncio
async def test_after_block_correct_password_also_rejected(client: httpx.AsyncClient) -> None:
    """限流后即便密码对也直接 429（早拦截在 check 阶段）。"""
    for _ in range(RL_THRESHOLD):
        await _bad_login(client)
    r = await _good_login(client)
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_success_resets_counter(client: httpx.AsyncClient) -> None:
    # 失败到差 1 次就限流
    for _ in range(RL_THRESHOLD - 1):
        r = await _bad_login(client)
        assert r.status_code == 401
    # 成功登录 → 计数清零
    ok = await _good_login(client)
    assert ok.status_code == 200
    # 再次失败 N-1 次仍然 401（counter 被重置过）
    for _ in range(RL_THRESHOLD - 1):
        r = await _bad_login(client)
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_per_ip_isolation(client: httpx.AsyncClient) -> None:
    """同一 username 从不同 IP 来时计数独立。"""
    for _ in range(RL_THRESHOLD):
        r = await _bad_login(client, ip="1.1.1.1")
    assert r.status_code == 429
    # 不同 IP，counter 应当独立
    r2 = await _bad_login(client, ip="2.2.2.2")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_per_username_isolation(client: httpx.AsyncClient) -> None:
    """同一 IP 不同 username 时计数独立。"""
    for _ in range(RL_THRESHOLD):
        r = await _bad_login(client, username="admin", ip="3.3.3.3")
    assert r.status_code == 429
    # 同 IP 换用户名不应被牵连
    r2 = await _bad_login(client, username="ghost", ip="3.3.3.3")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_no_limiter_means_no_throttling(app_state, db) -> None:
    """limiter=None 时无限失败也不会触发限流。"""
    app_state.login_rate_limiter = None
    app = create_app(state_builder=lambda: app_state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        for _ in range(RL_THRESHOLD * 3):
            r = await ac.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "WRONG"},
            )
            assert r.status_code == 401
