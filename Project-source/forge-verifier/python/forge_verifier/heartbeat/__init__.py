"""Verifier HTTP 心跳客户端。

与 forge-server 端 schema 对偶（独立实现，不共享代码）：
- 计算 HMAC（与 server 算法一致）
- 通过 httpx 调 POST /api/v1/licenses/{id}/heartbeat
- 解析服务端 HeartbeatResponse，把 anomaly / revoked 透传给业务层

设计：纯函数 + Client class。便于单测 mock。
"""
from forge_verifier.heartbeat.client import (
    HeartbeatClient,
    HeartbeatClientError,
    HeartbeatResult,
    compute_signature,
)

__all__ = [
    "HeartbeatClient",
    "HeartbeatClientError",
    "HeartbeatResult",
    "compute_signature",
]
