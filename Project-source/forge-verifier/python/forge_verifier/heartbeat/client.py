"""HTTP 心跳客户端。"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import httpx


API_KEY_HEADER = "X-Forge-API-Key"
DEFAULT_TIMEOUT_SECONDS = 5.0


class HeartbeatClientError(Exception):
    """心跳调用失败基类。"""


def compute_signature(
    *,
    license_id: str,
    fingerprint: str,
    reported_at: datetime,
    nonce: str,
    verifier_version: str,
    api_key: str,
) -> str:
    """与 server 侧 compute_signature 算法一致；独立实现，不 import server 代码。"""
    body = {
        "fingerprint": fingerprint,
        "license_id": license_id,
        "nonce": nonce,
        "reported_at": reported_at.astimezone(timezone.utc).isoformat(),
        "verifier_version": verifier_version,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(api_key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class HeartbeatResult:
    """服务端响应解析结果。"""

    license_status: Literal["valid", "expired", "revoked"]
    multi_env_anomaly: bool
    next_heartbeat_after_seconds: int
    server_time: datetime


class HeartbeatClient:
    """对 LA `/heartbeat` 的轻量 client。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        verifier_version: str = "forge-verifier/python@0.1.0",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._verifier_version = verifier_version
        self._timeout = timeout_seconds

    async def send(
        self,
        *,
        license_id: str,
        fingerprint: str,
        now: datetime | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> HeartbeatResult:
        """发送单次心跳。

        Args:
            client: 测试期可注入；生产由本方法自建短连接
        """
        reported_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        nonce = secrets.token_hex(16)
        signature = compute_signature(
            license_id=license_id,
            fingerprint=fingerprint,
            reported_at=reported_at,
            nonce=nonce,
            verifier_version=self._verifier_version,
            api_key=self._api_key,
        )
        body = {
            "license_id": license_id,
            "fingerprint": fingerprint,
            "reported_at": reported_at.isoformat(),
            "nonce": nonce,
            "verifier_version": self._verifier_version,
            "signature": signature,
        }
        url = f"{self._base_url}/api/v1/licenses/{license_id}/heartbeat"
        headers = {API_KEY_HEADER: self._api_key}

        async def _do(c: httpx.AsyncClient) -> httpx.Response:
            return await c.post(url, json=body, headers=headers, timeout=self._timeout)

        if client is not None:
            response = await _do(client)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                response = await _do(c)

        if response.status_code != 200:
            raise HeartbeatClientError(
                f"heartbeat HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
            return HeartbeatResult(
                license_status=data["license_status"],
                multi_env_anomaly=bool(data["multi_env_anomaly"]),
                next_heartbeat_after_seconds=int(data["next_heartbeat_after_seconds"]),
                server_time=datetime.fromisoformat(data["server_time"]),
            )
        except (KeyError, ValueError) as exc:
            raise HeartbeatClientError(f"malformed heartbeat response: {exc}") from exc
