"""HeartbeatClient 端到端：用 httpx MockTransport 模拟 LA 响应。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from forge_verifier.heartbeat import (
    HeartbeatClient,
    HeartbeatClientError,
    compute_signature,
)


def _ok_response_factory(*, anomaly: bool = False, status: str = "valid"):
    """构造一份模拟 LA `/heartbeat` 响应。"""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # 服务端会回 200 + HeartbeatResponse
        return httpx.Response(
            200,
            json={
                "license_status": status,
                "multi_env_anomaly": anomaly,
                "next_heartbeat_after_seconds": 3600,
                "server_time": datetime.now(timezone.utc).isoformat(),
            },
        )
    return handler


def _captures_factory():
    """捕获所有请求供断言用。"""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "license_status": "valid",
                "multi_env_anomaly": False,
                "next_heartbeat_after_seconds": 3600,
                "server_time": datetime.now(timezone.utc).isoformat(),
            },
        )

    return handler, captured


# ────────────────────────────────────────────────────────────


def test_compute_signature_matches_server_side() -> None:
    """Verifier 端 compute_signature 与 forge-server 端算法一致（无 import 共享）。"""
    sig = compute_signature(
        license_id="lic-1",
        fingerprint="fp-1",
        reported_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=timezone.utc),
        nonce="abc",
        verifier_version="test/1.0",
        api_key="key-1",
    )
    # 同样的输入两次结果一致
    sig2 = compute_signature(
        license_id="lic-1",
        fingerprint="fp-1",
        reported_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=timezone.utc),
        nonce="abc",
        verifier_version="test/1.0",
        api_key="key-1",
    )
    assert sig == sig2
    # 不同 api_key 结果不同
    sig_alt = compute_signature(
        license_id="lic-1",
        fingerprint="fp-1",
        reported_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=timezone.utc),
        nonce="abc",
        verifier_version="test/1.0",
        api_key="key-2",
    )
    assert sig != sig_alt


@pytest.mark.asyncio
async def test_send_heartbeat_success() -> None:
    handler = _ok_response_factory()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        c = HeartbeatClient(base_url="https://la.example.com", api_key="api-key")
        result = await c.send(
            license_id="lic-1",
            fingerprint="fp-1",
            client=client,
        )
        assert result.license_status == "valid"
        assert result.multi_env_anomaly is False
        assert result.next_heartbeat_after_seconds == 3600


@pytest.mark.asyncio
async def test_send_heartbeat_anomaly_propagated() -> None:
    handler = _ok_response_factory(anomaly=True)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        c = HeartbeatClient(base_url="https://la.example.com", api_key="api-key")
        result = await c.send(license_id="lic-1", fingerprint="fp-1", client=client)
        assert result.multi_env_anomaly is True


@pytest.mark.asyncio
async def test_send_heartbeat_revoked() -> None:
    handler = _ok_response_factory(status="revoked")
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        c = HeartbeatClient(base_url="https://la.example.com", api_key="api-key")
        result = await c.send(license_id="lic-1", fingerprint="fp-1", client=client)
        assert result.license_status == "revoked"


@pytest.mark.asyncio
async def test_send_heartbeat_4xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid api key"})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        c = HeartbeatClient(base_url="https://la.example.com", api_key="bad")
        with pytest.raises(HeartbeatClientError, match="401"):
            await c.send(license_id="lic-1", fingerprint="fp-1", client=client)


@pytest.mark.asyncio
async def test_send_heartbeat_sends_api_key_header() -> None:
    handler, captures = _captures_factory()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        c = HeartbeatClient(base_url="https://la.example.com", api_key="my-api-key")
        await c.send(license_id="lic-1", fingerprint="fp-1", client=client)
        assert captures, "no request captured"
        req = captures[0]
        assert req.headers["X-Forge-API-Key"] == "my-api-key"
        body = json.loads(req.content)
        assert body["license_id"] == "lic-1"
        assert body["fingerprint"] == "fp-1"
        # 验证 signature 字段是合法 HMAC
        expected = compute_signature(
            license_id=body["license_id"],
            fingerprint=body["fingerprint"],
            reported_at=datetime.fromisoformat(body["reported_at"]),
            nonce=body["nonce"],
            verifier_version=body["verifier_version"],
            api_key="my-api-key",
        )
        assert body["signature"] == expected


@pytest.mark.asyncio
async def test_send_heartbeat_each_call_uses_fresh_nonce() -> None:
    handler, captures = _captures_factory()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        c = HeartbeatClient(base_url="https://la.example.com", api_key="k")
        await c.send(license_id="lic-1", fingerprint="fp-1", client=client)
        await c.send(license_id="lic-1", fingerprint="fp-1", client=client)
    nonces = {json.loads(r.content)["nonce"] for r in captures}
    assert len(nonces) == 2
