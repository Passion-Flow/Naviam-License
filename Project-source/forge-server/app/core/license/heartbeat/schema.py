"""Heartbeat 请求 / 响应 schema + HMAC 签名校验。

防重放设计：
- 请求含 `nonce`（随机 32 字节 hex）+ `reported_at`（UTC ISO）
- HMAC-SHA256 over canonical(license_id, fingerprint, reported_at, nonce) with key = api_key
- 服务端：
  1. 校验 HMAC（防伪造 / 防中间人篡改）
  2. reported_at 与服务器时钟差 ≤ 5 分钟（防重放 + 时钟漂移容忍）
  3. nonce 在最近 10 分钟内未见过（cache 短 TTL 去重）

注意：
- HMAC key 是 **api_key 的明文** —— api_key 不进库，仅哈希入库做认证比对
- 业务侧拿到 api_key 哈希记录后，用明文 api_key（请求 header 来的）当 HMAC key
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CLOCK_SKEW_TOLERANCE_SECONDS = 300       # 5 分钟
NONCE_TTL_SECONDS = 600                  # 10 分钟（cache 短 TTL 防重放）


class HeartbeatVerificationError(Exception):
    """Heartbeat 请求验证失败（伪造 / 重放 / 时钟漂移过大）。

    刻意只给笼统原因，避免侧信道泄露给攻击者。
    """


class HeartbeatRequest(BaseModel):
    """Verifier 上报的心跳请求体。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    license_id: str = Field(description="对应的 license ID")
    fingerprint: str = Field(description="当前部署指纹（SHA-256 hex）")
    reported_at: datetime = Field(description="Verifier 本地时间（UTC ISO 8601）")
    nonce: str = Field(min_length=16, max_length=128, description="单次唯一随机串")
    verifier_version: str = Field(default="forge-verifier/python@0.1.0", description="客户端版本（便于排障）")
    signature: str = Field(description="HMAC-SHA256(api_key, canonical(...)) hex")

    def canonical_for_hmac(self) -> bytes:
        """构造 HMAC 输入字节流（不含 signature 字段）。"""
        body = {
            "fingerprint": self.fingerprint,
            "license_id": self.license_id,
            "nonce": self.nonce,
            "reported_at": self.reported_at.astimezone(timezone.utc).isoformat(),
            "verifier_version": self.verifier_version,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


class HeartbeatResponse(BaseModel):
    """服务端对心跳的回复。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    license_status: Literal["valid", "expired", "revoked"] = Field(description="LA 端 license 当前状态")
    multi_env_anomaly: bool = Field(default=False, description="LA 端判定该 license 出现多环境异常")
    next_heartbeat_after_seconds: int = Field(description="客户端建议下次心跳间隔")
    server_time: datetime = Field(description="服务器 UTC 时间（client 用于时钟矫正）")


def compute_signature(request_without_sig: HeartbeatRequest, *, api_key: str) -> str:
    """计算 HMAC 用作 signature 字段（Verifier 侧 + Server 侧都用这个函数算）。"""
    if not api_key:
        raise ValueError("api_key must be non-empty")
    return hmac.new(
        api_key.encode("utf-8"),
        request_without_sig.canonical_for_hmac(),
        hashlib.sha256,
    ).hexdigest()


def verify_request(
    request: HeartbeatRequest,
    *,
    api_key: str,
    now: datetime | None = None,
    seen_nonce: bool = False,
) -> None:
    """对单个心跳请求做完整校验。不通过抛 HeartbeatVerificationError。

    seen_nonce: 由 collector 查 cache 后传入；True 表示该 nonce 在 TTL 内见过 → 重放。
    """
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    # 1. HMAC 校验（防伪造）
    expected = compute_signature(request, api_key=api_key)
    if not hmac.compare_digest(expected, request.signature):
        raise HeartbeatVerificationError("invalid signature")

    # 2. 时钟漂移
    delta = abs((request.reported_at.astimezone(timezone.utc) - now_utc).total_seconds())
    if delta > CLOCK_SKEW_TOLERANCE_SECONDS:
        raise HeartbeatVerificationError("reported_at outside allowed clock skew")

    # 3. nonce 防重放
    if seen_nonce:
        raise HeartbeatVerificationError("nonce already used (replay suspected)")
