"""结构化 request 日志 + Prometheus 埋点 中间件。

每个请求记录一条 JSON line（structlog 已 json 模式时自动）：
  ts / level=info / event=http.request / method / path / route / status / ms / request_id / actor

埋 metrics：
  forge_http_requests_total{method,route,status}
  forge_http_request_duration_seconds_{sum,count}{route}
"""
from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import PrometheusMetrics, _route_label

logger = structlog.get_logger("forge.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        # request_id：客户透传 → 落日志；否则生成
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            elapsed = time.perf_counter() - start
            route = _route_label(request)
            metrics: PrometheusMetrics | None = getattr(request.app.state, "metrics", None)
            if metrics is not None:
                metrics.inc_request(method=request.method, route=route, status=status)
                metrics.observe_latency(route=route, seconds=elapsed)
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                route=route,
                status=status,
                ms=round(elapsed * 1000, 2),
                request_id=rid,
                client=request.client.host if request.client else None,
            )

        # 把 request_id 回写给客户便于追踪
        response.headers.setdefault("x-request-id", rid)
        return response
