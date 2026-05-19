"""Prometheus exposition —— 零依赖最小实现，避免引入 prometheus_client。

目的：客户拿 ServiceMonitor 抓 /metrics 即可。指标集少而稳：
- forge_http_requests_total{method,route,status}
- forge_http_request_duration_seconds_sum/count{route} （简化 histogram → sum/count）

设计选择：不写 histogram bucket（实现复杂、序列化字节数大）。这套指标对
"接入难度 vs 价值" 取折中；客户要更精细可换 prometheus_client 第三方库。
"""
from __future__ import annotations

import threading
from collections import defaultdict
from time import perf_counter
from typing import Iterator

from fastapi import Request, Response


class PrometheusMetrics:
    """线程安全的最小指标集合（counter + sum/count）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key: (metric, frozenset of labels)
        self._counters: dict[tuple[str, frozenset[tuple[str, str]]], int] = defaultdict(int)
        self._timer_sum: dict[tuple[str, frozenset[tuple[str, str]]], float] = defaultdict(float)
        self._timer_count: dict[tuple[str, frozenset[tuple[str, str]]], int] = defaultdict(int)

    def inc_request(self, *, method: str, route: str, status: int) -> None:
        labels = frozenset({"method": method, "route": route, "status": str(status)}.items())
        with self._lock:
            self._counters[("forge_http_requests_total", labels)] += 1

    def observe_latency(self, *, route: str, seconds: float) -> None:
        labels = frozenset({"route": route}.items())
        with self._lock:
            self._timer_sum[("forge_http_request_duration_seconds_sum", labels)] += seconds
            self._timer_count[("forge_http_request_duration_seconds_count", labels)] += 1

    def expose(self) -> Iterator[str]:
        """生成 Prometheus text format。"""
        with self._lock:
            # 注释 + TYPE 行
            yield "# HELP forge_http_requests_total Total HTTP requests."
            yield "# TYPE forge_http_requests_total counter"
            for (metric, labels), value in self._counters.items():
                yield _fmt(metric, labels, value)
            yield "# HELP forge_http_request_duration_seconds Request latency."
            yield "# TYPE forge_http_request_duration_seconds summary"
            for (metric, labels), value in self._timer_sum.items():
                yield _fmt(metric, labels, value)
            for (metric, labels), value in self._timer_count.items():
                yield _fmt(metric, labels, value)


def _fmt(metric: str, labels: frozenset[tuple[str, str]], value: float | int) -> str:
    if not labels:
        return f"{metric} {value}"
    label_str = ",".join(f'{k}="{_escape(v)}"' for k, v in sorted(labels))
    return f"{metric}{{{label_str}}} {value}"


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")


async def metrics_endpoint(request: Request) -> Response:
    """GET /metrics —— 暴露 Prometheus text format。"""
    metrics: PrometheusMetrics = request.app.state.metrics
    body = "\n".join(metrics.expose()) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")


# RequestLoggingMiddleware 调用辅助
def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


def time_request(request: Request) -> "RequestTimer":
    return RequestTimer(request)


class RequestTimer:
    """`async with time_request(req) as t:` —— 进入即开始，退出时 observe。"""

    def __init__(self, request: Request) -> None:
        self._request = request
        self._start: float = 0.0

    def __enter__(self) -> "RequestTimer":
        self._start = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = perf_counter() - self._start
        metrics: PrometheusMetrics | None = getattr(self._request.app.state, "metrics", None)
        if metrics is not None:
            metrics.observe_latency(route=_route_label(self._request), seconds=elapsed)
