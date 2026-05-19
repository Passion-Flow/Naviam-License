"""Heartbeat 子模块。

业务流程：
1. Verifier 每个周期 → POST /api/v1/licenses/{id}/heartbeat
2. 服务端鉴权 (API Key) → 校验 HMAC → 防重放 (nonce + 时钟漂移) → 入库 + 入 cache
3. detection 检查 license 在最近 N 小时见过多少个不同指纹
4. 超阈值 → 写 audit + 标记 anomaly（不直接吊销，避免误杀；交由 admin / 自动策略决定）
"""
from app.core.license.heartbeat.collector import (
    HeartbeatCollector,
    HeartbeatRecord,
    InMemoryHeartbeatCollector,
)
from app.core.license.heartbeat.detector import (
    DetectionVerdict,
    MultiEnvDetector,
)
from app.core.license.heartbeat.schema import (
    HeartbeatRequest,
    HeartbeatResponse,
    HeartbeatVerificationError,
    compute_signature,
    verify_request,
)

__all__ = [
    "DetectionVerdict",
    "HeartbeatCollector",
    "HeartbeatRecord",
    "HeartbeatRequest",
    "HeartbeatResponse",
    "HeartbeatVerificationError",
    "InMemoryHeartbeatCollector",
    "MultiEnvDetector",
    "compute_signature",
    "verify_request",
]
