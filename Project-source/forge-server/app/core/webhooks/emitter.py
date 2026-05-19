"""Webhook 推送器。

设计：
- POST 到 `settings.webhook_url`；空 → 静默跳过（不强制开）
- HMAC-SHA256 签名 body，密钥 = `settings.webhook_signing_secret`
- header `X-Forge-Event` = 事件类型（如 `license.issued`）
- header `X-Forge-Signature` = `sha256=<hex digest>`
- 重试策略：失败仅记日志（best-effort）；不阻塞业务请求

为什么不入队 / 不用 Celery：
- 业务路径写 webhook 是 best-effort；下游慢不能拖 LA 慢
- 已 fire-and-forget 用 `asyncio.create_task`
- 如果客户要可靠投递，把 webhook_url 指向他们自己的 ingest 队列（Kafka / NATS）
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

import httpx
import structlog

from app.settings import get_settings

logger = structlog.get_logger("forge.webhooks")


class WebhookEmitter:
    def __init__(self, *, url: str, signing_secret: str, timeout_seconds: float = 5.0) -> None:
        self._url = url
        self._secret = signing_secret.encode("utf-8")
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        body = json.dumps(
            {"event": event_type, "data": payload}, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        signature = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Forge-Event": event_type,
                        "X-Forge-Signature": f"sha256={signature}",
                    },
                )
                if response.status_code >= 400:
                    logger.warning(
                        "webhook.delivery_failed",
                        event=event_type,
                        status=response.status_code,
                        body=response.text[:512],
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("webhook.delivery_error", event=event_type, error=str(exc))


def build_emitter() -> WebhookEmitter:
    s = get_settings()
    return WebhookEmitter(url=s.webhook_url, signing_secret=s.webhook_signing_secret)


async def emit_event(event_type: str, payload: dict[str, Any]) -> None:
    """便捷入口；不阻塞调用方（fire-and-forget）。"""
    emitter = build_emitter()
    if not emitter.enabled:
        return
    # 异步触发 + 弃任务（业务路径不应阻塞）
    asyncio.create_task(emitter.emit(event_type, payload))
