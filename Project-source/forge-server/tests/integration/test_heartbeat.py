"""Heartbeat 协议 + 多环境检测端到端测试。

覆盖：
- HMAC 校验通过 / 篡改 / 错 api_key
- 时钟漂移容忍 / 拒绝
- nonce 防重放
- 多环境检测（同 license 在多指纹上报 → anomaly）
- 容器场景的 grace_count
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.license.heartbeat import (
    HeartbeatRequest,
    HeartbeatRecord,
    HeartbeatVerificationError,
    InMemoryHeartbeatCollector,
    MultiEnvDetector,
    compute_signature,
    verify_request,
)


def _build_request(
    *,
    license_id: str = "lic-001",
    fingerprint: str = "fp-A",
    api_key: str = "secret-key-xxx",
    reported_at: datetime | None = None,
    nonce: str | None = None,
) -> HeartbeatRequest:
    """构造一份合法签名的 HeartbeatRequest。"""
    now = reported_at or datetime.now(timezone.utc)
    unsigned = HeartbeatRequest(
        license_id=license_id,
        fingerprint=fingerprint,
        reported_at=now,
        nonce=nonce or secrets.token_hex(16),
        signature="",  # 占位
    )
    sig = compute_signature(unsigned, api_key=api_key)
    return unsigned.model_copy(update={"signature": sig})


# ────────────────────────────────────────────────────────────
# Schema + HMAC
# ────────────────────────────────────────────────────────────

def test_verify_request_accepts_valid_signature() -> None:
    req = _build_request(api_key="api-key-1")
    verify_request(req, api_key="api-key-1")  # no exception


def test_verify_request_rejects_wrong_api_key() -> None:
    req = _build_request(api_key="api-key-1")
    with pytest.raises(HeartbeatVerificationError, match="invalid signature"):
        verify_request(req, api_key="api-key-2")


def test_verify_request_rejects_tampered_fingerprint() -> None:
    req = _build_request(api_key="api-key-1", fingerprint="fp-A")
    # 同一 signature 但 fingerprint 被替换 → HMAC 失败
    tampered = req.model_copy(update={"fingerprint": "fp-B"})
    with pytest.raises(HeartbeatVerificationError, match="invalid signature"):
        verify_request(tampered, api_key="api-key-1")


def test_verify_request_rejects_clock_skew() -> None:
    far_future = datetime.now(timezone.utc) + timedelta(minutes=10)
    req = _build_request(api_key="api-key-1", reported_at=far_future)
    with pytest.raises(HeartbeatVerificationError, match="clock skew"):
        verify_request(req, api_key="api-key-1")


def test_verify_request_accepts_within_tolerance() -> None:
    """4 分钟漂移在 5 分钟容忍内 → 通过。"""
    slight = datetime.now(timezone.utc) - timedelta(minutes=4)
    req = _build_request(api_key="api-key-1", reported_at=slight)
    verify_request(req, api_key="api-key-1")


def test_verify_request_rejects_replayed_nonce() -> None:
    req = _build_request(api_key="api-key-1")
    with pytest.raises(HeartbeatVerificationError, match="replay"):
        verify_request(req, api_key="api-key-1", seen_nonce=True)


# ────────────────────────────────────────────────────────────
# Collector
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_collector_records_and_lists_fingerprints() -> None:
    collector = InMemoryHeartbeatCollector()
    now = datetime.now(timezone.utc)
    for fp in ["fp-A", "fp-A", "fp-B"]:
        await collector.record(
            HeartbeatRecord(
                license_id="lic-1",
                fingerprint=fp,
                received_at=now,
                reported_at=now,
                nonce=secrets.token_hex(16),
                api_key_id="ak-1",
                verifier_version="test",
            )
        )
    fps = await collector.recent_fingerprints("lic-1", window=timedelta(hours=1), now=now)
    assert fps == {"fp-A", "fp-B"}


@pytest.mark.asyncio
async def test_collector_filters_by_window() -> None:
    collector = InMemoryHeartbeatCollector()
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=48)
    recent = now - timedelta(minutes=10)
    for received_at, fp in [(old, "fp-OLD"), (recent, "fp-RECENT")]:
        await collector.record(
            HeartbeatRecord(
                license_id="lic-1",
                fingerprint=fp,
                received_at=received_at,
                reported_at=received_at,
                nonce=secrets.token_hex(16),
                api_key_id="ak-1",
                verifier_version="test",
            )
        )
    fps = await collector.recent_fingerprints("lic-1", window=timedelta(hours=24), now=now)
    assert fps == {"fp-RECENT"}


@pytest.mark.asyncio
async def test_collector_nonce_replay_detection() -> None:
    collector = InMemoryHeartbeatCollector()
    assert not await collector.is_nonce_seen("lic-1", "nonce-A")
    await collector.mark_nonce_seen("lic-1", "nonce-A")
    assert await collector.is_nonce_seen("lic-1", "nonce-A")
    # 不同 license 同 nonce 不冲突
    assert not await collector.is_nonce_seen("lic-2", "nonce-A")


# ────────────────────────────────────────────────────────────
# MultiEnvDetector
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detector_clean_when_single_fingerprint() -> None:
    collector = InMemoryHeartbeatCollector()
    now = datetime.now(timezone.utc)
    for _ in range(10):
        await collector.record(
            HeartbeatRecord(
                license_id="lic-1",
                fingerprint="fp-A",
                received_at=now,
                reported_at=now,
                nonce=secrets.token_hex(16),
                api_key_id="ak-1",
                verifier_version="test",
            )
        )
    detector = MultiEnvDetector(window=timedelta(hours=24), threshold=1)
    verdict = await detector.evaluate("lic-1", collector=collector, now=now)
    assert verdict.anomaly is False
    assert verdict.distinct_fingerprint_count == 1


@pytest.mark.asyncio
async def test_detector_flags_anomaly_for_multiple_fingerprints() -> None:
    """同一 license 在 2 个不同指纹上心跳 → anomaly。"""
    collector = InMemoryHeartbeatCollector()
    now = datetime.now(timezone.utc)
    for fp in ["fp-A", "fp-B"]:
        await collector.record(
            HeartbeatRecord(
                license_id="lic-1",
                fingerprint=fp,
                received_at=now,
                reported_at=now,
                nonce=secrets.token_hex(16),
                api_key_id="ak-1",
                verifier_version="test",
            )
        )
    detector = MultiEnvDetector(window=timedelta(hours=24), threshold=1)
    verdict = await detector.evaluate("lic-1", collector=collector, now=now)
    assert verdict.anomaly is True
    assert verdict.distinct_fingerprint_count == 2
    assert "observed 2 distinct fingerprints" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_detector_respects_grace_count_for_container_churn() -> None:
    """容器频繁重建场景：threshold=1 + grace=2 → 允许同时 3 个指纹。"""
    collector = InMemoryHeartbeatCollector()
    now = datetime.now(timezone.utc)
    for fp in ["fp-A", "fp-B", "fp-C"]:
        await collector.record(
            HeartbeatRecord(
                license_id="lic-1",
                fingerprint=fp,
                received_at=now,
                reported_at=now,
                nonce=secrets.token_hex(16),
                api_key_id="ak-1",
                verifier_version="test",
            )
        )
    detector = MultiEnvDetector(window=timedelta(hours=24), threshold=1, grace_count=2)
    verdict = await detector.evaluate("lic-1", collector=collector, now=now)
    assert verdict.anomaly is False  # 3 ≤ threshold(1) + grace(2)

    # 第 4 个指纹超出 grace → anomaly
    await collector.record(
        HeartbeatRecord(
            license_id="lic-1",
            fingerprint="fp-D",
            received_at=now,
            reported_at=now,
            nonce=secrets.token_hex(16),
            api_key_id="ak-1",
            verifier_version="test",
        )
    )
    verdict = await detector.evaluate("lic-1", collector=collector, now=now)
    assert verdict.anomaly is True
    assert verdict.distinct_fingerprint_count == 4


@pytest.mark.asyncio
async def test_detector_window_isolates_old_data() -> None:
    """老指纹超出窗口不再计入。"""
    collector = InMemoryHeartbeatCollector()
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)
    for received_at, fp in [
        (old, "fp-OLD-A"),
        (old, "fp-OLD-B"),
        (now, "fp-CURRENT"),
    ]:
        await collector.record(
            HeartbeatRecord(
                license_id="lic-1",
                fingerprint=fp,
                received_at=received_at,
                reported_at=received_at,
                nonce=secrets.token_hex(16),
                api_key_id="ak-1",
                verifier_version="test",
            )
        )
    detector = MultiEnvDetector(window=timedelta(hours=24), threshold=1)
    verdict = await detector.evaluate("lic-1", collector=collector, now=now)
    assert verdict.anomaly is False  # 老的 2 个不在 24h 窗内
    assert verdict.distinct_fingerprint_count == 1


# ────────────────────────────────────────────────────────────
# 端到端 — verifier → server 完整流（mock 服务端处理）
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_clone_detected_after_two_environments() -> None:
    """完整剧本：客户 A 心跳 OK，客户 B 拷 license 心跳 → 检测出多环境占用。"""
    api_key = "api-key-customer-X"
    license_id = "lic-shared-by-clone"
    collector = InMemoryHeartbeatCollector()
    detector = MultiEnvDetector(window=timedelta(hours=24), threshold=1)
    now = datetime.now(timezone.utc)

    # 客户 A 心跳
    req_a = _build_request(license_id=license_id, fingerprint="fp-customer-A", api_key=api_key)
    verify_request(req_a, api_key=api_key, now=now)
    seen = await collector.is_nonce_seen(req_a.license_id, req_a.nonce)
    assert seen is False
    await collector.mark_nonce_seen(req_a.license_id, req_a.nonce)
    await collector.record(
        HeartbeatRecord(
            license_id=req_a.license_id,
            fingerprint=req_a.fingerprint,
            received_at=now,
            reported_at=req_a.reported_at,
            nonce=req_a.nonce,
            api_key_id="ak-1",
            verifier_version=req_a.verifier_version,
        )
    )
    verdict_after_a = await detector.evaluate(license_id, collector=collector, now=now)
    assert verdict_after_a.anomaly is False

    # 客户 B（拿到拷贝）心跳
    req_b = _build_request(license_id=license_id, fingerprint="fp-customer-B", api_key=api_key)
    verify_request(req_b, api_key=api_key, now=now)
    await collector.mark_nonce_seen(req_b.license_id, req_b.nonce)
    await collector.record(
        HeartbeatRecord(
            license_id=req_b.license_id,
            fingerprint=req_b.fingerprint,
            received_at=now,
            reported_at=req_b.reported_at,
            nonce=req_b.nonce,
            api_key_id="ak-1",
            verifier_version=req_b.verifier_version,
        )
    )
    verdict_after_b = await detector.evaluate(license_id, collector=collector, now=now)
    assert verdict_after_b.anomaly is True
    assert verdict_after_b.distinct_fingerprint_count == 2
