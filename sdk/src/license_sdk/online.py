"""在线心跳（可选）。

仅在用户安装 license-sdk[online] 时可用。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OnlineConfig:
    """在线模式配置。

    - endpoint: Console base URL（不含路径，例如 https://license.example.com）。
    - heartbeat_interval_seconds: 心跳周期。
    - mtls_client_cert_path / mtls_client_key_path: 产品镜像内置的 client cert。
      （V1 默认强制 mTLS；不允许降级到普通 HTTPS。）
    - timeout_seconds: 单次 RPC 超时。
    """

    endpoint: str
    heartbeat_interval_seconds: int = 3600
    mtls_client_cert_path: str | None = None
    mtls_client_key_path: str | None = None
    timeout_seconds: float = 5.0


# 真实的心跳实现（依赖 httpx）放在 client.py 里按需 import；
# 这里只暴露配置类，避免在没有装 [online] extra 时 import 失败。
