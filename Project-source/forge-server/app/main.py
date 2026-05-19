"""
Forge Server — FastAPI app entry.

启动入口由仓库根的 `main.py` 调用，本模块只导出 `app`。
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI

from app.api.v1 import router as api_v1_router
from app.middleware.default_password_lockout import DefaultPasswordLockoutMiddleware
from app.middleware.mtls_gate import MtlsGateMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.observability.metrics import PrometheusMetrics, metrics_endpoint
from app.observability.startup_checks import StartupCheckError, run_startup_checks
from app.settings import get_settings
from app.state import AppState, build_state

logger = logging.getLogger("forge.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 默认装配：从 settings 构造 AppState（除非测试已预置）
    if not getattr(app.state, "forge_state", None):
        app.state.forge_state = build_state(get_settings())
    state = app.state.forge_state

    # adapter 显式连接 —— 测试路径自行注入已连好的实例时跳过
    if state.database is not None:
        await state.database.connect()
    # session_store 与 login_rate_limiter 共享底层 Cache，需要逐个 connect
    for cache_holder in (state.session_store, state.login_rate_limiter):
        cache = getattr(cache_holder, "_cache", None)
        connect = getattr(cache, "connect", None)
        if connect is not None:
            await connect()

    # 启动期健康自检：DB ping + Cache ping + KeyStorage 可读
    # 失败时按 settings.startup_strict 决定 abort 还是仅记录
    try:
        await run_startup_checks(state)
    except StartupCheckError as exc:
        if state.settings.startup_strict:
            logger.error("startup checks failed: %s", exc)
            # 结构化失败退出：让 k8s liveness 立刻看到 1 号码退出
            sys.exit(1)
        else:
            logger.warning("startup checks failed (non-strict): %s", exc)

    try:
        yield
    finally:
        # 关闭时反向 disconnect
        for cache_holder in (state.session_store, state.login_rate_limiter):
            cache = getattr(cache_holder, "_cache", None)
            disconnect = getattr(cache, "disconnect", None)
            if disconnect is not None:
                await disconnect()
        if state.database is not None:
            await state.database.disconnect()


def create_app(state_builder: Callable[[], AppState] | None = None) -> FastAPI:
    """构造 FastAPI 实例。

    Args:
        state_builder: 测试期可注入自定义 state（覆盖默认 build_state）
    """
    app = FastAPI(
        title="Forge License Authority",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(api_v1_router, prefix="/api/v1")
    # 结构化 request 日志 + Prometheus 指标埋点（最外层，记录全部请求）
    app.state.metrics = PrometheusMetrics()
    app.add_middleware(RequestLoggingMiddleware)
    # Default-password strict-mode 写操作锁；不启用时该中间件等同于 no-op
    app.add_middleware(DefaultPasswordLockoutMiddleware)
    # mTLS 闸门（settings.verifier_api_require_mtls=True 时生效）
    app.add_middleware(MtlsGateMiddleware)
    # Prometheus 暴露点 —— 部署到 forge-api 上；客户在 ServiceMonitor 抓
    app.add_api_route(
        "/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False
    )

    if state_builder is not None:
        app.state.forge_state = state_builder()
    return app


app = create_app()
