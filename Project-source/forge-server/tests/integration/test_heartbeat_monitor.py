"""Heartbeat 监控端到端：
- list / summary / detail 三端点 admin only（API Key 一律 401）
- list：按 license_id / since / until 过滤 + 分页
- summary：聚合 license 总数 / 独立指纹数 / last_seen / last_fingerprint，按 last_seen desc
- summary：单指纹 + threshold=1 → anomaly=False；多指纹 → anomaly=True
- detail：404 / drill-down 含 recent / fingerprints_seen / verdict
- detail：异常 license 的 verdict.anomaly=True 且 reason 非空
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
from app.core.license.heartbeat import HeartbeatRecord, MultiEnvDetector
from app.main import create_app
from app.middleware.api_key_auth import API_KEY_HEADER
from app.models import Base
from app.repositories import (
    ApiKeyRepository,
    AuditLogRepository,
    DbBackedApiKeyAuth,
    DbBackedHeartbeatCollector,
    DbBackedRevocationStore,
    HeartbeatQueryRepository,
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
    _, api_plain = await api_key_repo.issue(customer_id="c", project_label="p")

    # DB-backed collector so both query repo and detector see the same data
    collector = DbBackedHeartbeatCollector(db)
    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=revocation_store,
        crl_manager=CrlManager(store=revocation_store, key_storage=key_storage, algorithm="ed25519"),
        heartbeat_collector=collector,
        # threshold=1, grace=0 → 一个 license 出现 2 个指纹就 anomaly
        multi_env_detector=MultiEnvDetector(window=timedelta(hours=24), threshold=1),
        api_keys={},
        database=db,
        license_repository=LicenseRepository(db),
        api_key_auth=DbBackedApiKeyAuth(api_key_repo),
        api_key_repository=api_key_repo,
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
        audit_log_repository=AuditLogRepository(db),
        heartbeat_query_repository=HeartbeatQueryRepository(db),
    )
    return state, api_plain, collector


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
def collector(app_state) -> DbBackedHeartbeatCollector:
    return app_state[2]


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200


async def _seed_heartbeat(
    collector: DbBackedHeartbeatCollector,
    *,
    license_id: str,
    fingerprint: str,
    received_at: datetime,
    reported_at: datetime | None = None,
    nonce: str = "",
    api_key_id: str | None = None,
) -> None:
    await collector.record(HeartbeatRecord(
        license_id=license_id,
        fingerprint=fingerprint,
        received_at=received_at,
        reported_at=reported_at or received_at,
        nonce=nonce or f"n-{fingerprint}-{received_at.timestamp()}",
        api_key_id=api_key_id,
        verifier_version="1.0.0",
    ))


# ─────────────── auth ───────────────


@pytest.mark.asyncio
async def test_endpoints_reject_api_key(
    client: httpx.AsyncClient, api_key: str
) -> None:
    h = {API_KEY_HEADER: api_key}
    assert (await client.get("/api/v1/heartbeats", headers=h)).status_code == 401
    assert (await client.get("/api/v1/heartbeats/summary", headers=h)).status_code == 401
    assert (await client.get("/api/v1/heartbeats/anything", headers=h)).status_code == 401


# ─────────────── list ───────────────


@pytest.mark.asyncio
async def test_list_empty(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/v1/heartbeats")
    assert r.status_code == 200
    assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_list_returns_recent_desc(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    await _login(client)
    now = datetime.now(timezone.utc)
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(minutes=5))
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(minutes=1))
    await _seed_heartbeat(collector, license_id="lic-B", fingerprint="fp-X", received_at=now)

    r = await client.get("/api/v1/heartbeats")
    items = r.json()["items"]
    assert len(items) == 3
    # 倒序：最新的（lic-B）应当排第一
    assert items[0]["license_id"] == "lic-B"


@pytest.mark.asyncio
async def test_list_filters_by_license(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    await _login(client)
    now = datetime.now(timezone.utc)
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(seconds=10))
    await _seed_heartbeat(collector, license_id="lic-B", fingerprint="fp-2", received_at=now)

    r = await client.get("/api/v1/heartbeats", params={"license_id": "lic-A"})
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["license_id"] == "lic-A"


@pytest.mark.asyncio
async def test_list_pagination(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    await _login(client)
    now = datetime.now(timezone.utc)
    for i in range(5):
        await _seed_heartbeat(
            collector, license_id="lic-A", fingerprint="fp-1",
            received_at=now - timedelta(seconds=i),
        )

    r = await client.get("/api/v1/heartbeats", params={"limit": 2, "offset": 0})
    body = r.json()
    assert body["limit"] == 2
    assert len(body["items"]) == 2


# ─────────────── summary ───────────────


@pytest.mark.asyncio
async def test_summary_empty(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/v1/heartbeats/summary")
    assert r.status_code == 200
    assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_summary_aggregates(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    await _login(client)
    now = datetime.now(timezone.utc)
    # lic-A 出现 3 次同一指纹
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(minutes=10))
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(minutes=5))
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(seconds=1))
    # lic-B 出现 2 个不同指纹
    await _seed_heartbeat(collector, license_id="lic-B", fingerprint="fp-X", received_at=now - timedelta(minutes=2))
    await _seed_heartbeat(collector, license_id="lic-B", fingerprint="fp-Y", received_at=now - timedelta(seconds=10))

    r = await client.get("/api/v1/heartbeats/summary")
    items = r.json()["items"]
    by_lic = {it["license_id"]: it for it in items}
    assert by_lic["lic-A"]["total_count"] == 3
    assert by_lic["lic-A"]["distinct_fingerprint_count"] == 1
    assert by_lic["lic-A"]["last_fingerprint"] == "fp-1"
    assert by_lic["lic-A"]["anomaly"] is False

    assert by_lic["lic-B"]["total_count"] == 2
    assert by_lic["lic-B"]["distinct_fingerprint_count"] == 2
    # lic-B 在 24h 窗口内有 2 个指纹 > threshold=1 → anomaly
    assert by_lic["lic-B"]["anomaly"] is True
    assert by_lic["lic-B"]["anomaly_reason"] is not None
    assert by_lic["lic-B"]["threshold"] == 1


@pytest.mark.asyncio
async def test_summary_orders_by_last_seen_desc(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    await _login(client)
    now = datetime.now(timezone.utc)
    await _seed_heartbeat(collector, license_id="lic-OLD", fingerprint="f1", received_at=now - timedelta(hours=2))
    await _seed_heartbeat(collector, license_id="lic-NEW", fingerprint="f2", received_at=now - timedelta(seconds=5))

    items = (await client.get("/api/v1/heartbeats/summary")).json()["items"]
    assert items[0]["license_id"] == "lic-NEW"
    assert items[1]["license_id"] == "lic-OLD"


# ─────────────── detail ───────────────


@pytest.mark.asyncio
async def test_detail_404_when_no_heartbeats(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/v1/heartbeats/ghost-license")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detail_drill_down(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    await _login(client)
    now = datetime.now(timezone.utc)
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(minutes=3))
    await _seed_heartbeat(collector, license_id="lic-A", fingerprint="fp-1", received_at=now - timedelta(minutes=1))

    r = await client.get("/api/v1/heartbeats/lic-A")
    assert r.status_code == 200
    body = r.json()
    assert body["license_id"] == "lic-A"
    assert len(body["recent_heartbeats"]) == 2
    assert {fp["fingerprint"] for fp in body["fingerprints_seen"]} == {"fp-1"}
    assert body["verdict"]["anomaly"] is False
    assert body["verdict"]["distinct_fingerprint_count"] == 1


@pytest.mark.asyncio
async def test_detail_flags_anomaly(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    await _login(client)
    now = datetime.now(timezone.utc)
    await _seed_heartbeat(collector, license_id="lic-X", fingerprint="fp-1", received_at=now - timedelta(minutes=10))
    await _seed_heartbeat(collector, license_id="lic-X", fingerprint="fp-2", received_at=now - timedelta(minutes=5))
    await _seed_heartbeat(collector, license_id="lic-X", fingerprint="fp-3", received_at=now)

    body = (await client.get("/api/v1/heartbeats/lic-X")).json()
    assert body["verdict"]["anomaly"] is True
    assert body["verdict"]["distinct_fingerprint_count"] == 3
    assert body["verdict"]["reason"] is not None
    fps = {fp["fingerprint"] for fp in body["fingerprints_seen"]}
    assert fps == {"fp-1", "fp-2", "fp-3"}


@pytest.mark.asyncio
async def test_detail_since_seconds_window(
    client: httpx.AsyncClient, collector: DbBackedHeartbeatCollector
) -> None:
    """超出 since 窗口的心跳应被过滤掉。"""
    await _login(client)
    now = datetime.now(timezone.utc)
    # 老的 5 小时前；新的 1 秒前
    await _seed_heartbeat(collector, license_id="lic-W", fingerprint="old-fp", received_at=now - timedelta(hours=5))
    await _seed_heartbeat(collector, license_id="lic-W", fingerprint="new-fp", received_at=now - timedelta(seconds=1))

    # 窗口 10 分钟 → 只能看到 new-fp
    r = await client.get("/api/v1/heartbeats/lic-W", params={"since_seconds": 600})
    body = r.json()
    fps = {fp["fingerprint"] for fp in body["fingerprints_seen"]}
    assert fps == {"new-fp"}
