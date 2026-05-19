"""DbBackedHeartbeatCollector 测试 —— 跨进程持久化心跳数据。"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.database.postgres.adapter import PostgresDatabase
from app.core.license.heartbeat import HeartbeatRecord, MultiEnvDetector
from app.models import Base
from app.repositories import DbBackedHeartbeatCollector


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


@pytest.mark.asyncio
async def test_record_and_recent_fingerprints(db) -> None:
    collector = DbBackedHeartbeatCollector(db)
    now = datetime.now(timezone.utc)

    for fp in ["fp-A", "fp-A", "fp-B"]:
        await collector.record(HeartbeatRecord(
            license_id="lic-1",
            fingerprint=fp,
            received_at=now,
            reported_at=now,
            nonce=secrets.token_hex(16),
            api_key_id="ak",
            verifier_version="test",
        ))

    fingerprints = await collector.recent_fingerprints("lic-1", window=timedelta(hours=1), now=now)
    assert fingerprints == {"fp-A", "fp-B"}


@pytest.mark.asyncio
async def test_window_excludes_old_records(db) -> None:
    collector = DbBackedHeartbeatCollector(db)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)

    await collector.record(HeartbeatRecord(
        license_id="lic-1", fingerprint="fp-OLD",
        received_at=old, reported_at=old,
        nonce=secrets.token_hex(16), api_key_id="ak", verifier_version="t",
    ))
    await collector.record(HeartbeatRecord(
        license_id="lic-1", fingerprint="fp-NEW",
        received_at=now, reported_at=now,
        nonce=secrets.token_hex(16), api_key_id="ak", verifier_version="t",
    ))

    fps = await collector.recent_fingerprints("lic-1", window=timedelta(hours=24), now=now)
    assert fps == {"fp-NEW"}


@pytest.mark.asyncio
async def test_nonce_dedup(db) -> None:
    collector = DbBackedHeartbeatCollector(db)
    assert not await collector.is_nonce_seen("lic-1", "n1")
    await collector.mark_nonce_seen("lic-1", "n1")
    assert await collector.is_nonce_seen("lic-1", "n1")

    # 重复标记不抛异常（幂等）
    await collector.mark_nonce_seen("lic-1", "n1")
    assert await collector.is_nonce_seen("lic-1", "n1")

    # 不同 license 同 nonce 不冲突
    assert not await collector.is_nonce_seen("lic-2", "n1")


@pytest.mark.asyncio
async def test_persistence_across_collector_instances(db) -> None:
    """同一 DB，第二个 collector 实例能看到第一个写的记录。"""
    c1 = DbBackedHeartbeatCollector(db)
    now = datetime.now(timezone.utc)
    await c1.record(HeartbeatRecord(
        license_id="lic-1", fingerprint="fp-X",
        received_at=now, reported_at=now,
        nonce=secrets.token_hex(16), api_key_id=None, verifier_version="t",
    ))

    c2 = DbBackedHeartbeatCollector(db)
    fps = await c2.recent_fingerprints("lic-1", window=timedelta(hours=1), now=now)
    assert fps == {"fp-X"}


@pytest.mark.asyncio
async def test_multi_env_detector_with_db_collector(db) -> None:
    """detector 用 DB-backed collector → 多环境 anomaly 检测仍生效。"""
    collector = DbBackedHeartbeatCollector(db)
    detector = MultiEnvDetector(window=timedelta(hours=24), threshold=1)
    now = datetime.now(timezone.utc)

    for fp in ["fp-1", "fp-2"]:
        await collector.record(HeartbeatRecord(
            license_id="lic-1", fingerprint=fp,
            received_at=now, reported_at=now,
            nonce=secrets.token_hex(16), api_key_id=None, verifier_version="t",
        ))

    verdict = await detector.evaluate("lic-1", collector=collector, now=now)
    assert verdict.anomaly is True
    assert verdict.distinct_fingerprint_count == 2
