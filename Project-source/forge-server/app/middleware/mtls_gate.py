"""mTLS gate —— 当 settings.verifier_api_require_mtls=True 时，所有
`/api/v1/licenses/*` Verifier 调用必须经过客户端证书认证。

实现策略：Forge 不直接 terminate TLS。落地路径：
  Verifier ──mTLS──> nginx / ingress controller ──HTTP──> forge-api

nginx / ingress 把校验过的客户端证书 subject 通过 header 透传：
  X-Forwarded-Client-Cert: <subject DN>
  X-SSL-Client-Verify: SUCCESS

本中间件做的事：
  - 启用时检查 `X-SSL-Client-Verify == "SUCCESS"`
  - 否则 403
  - 不解析 cert subject（由上游 nginx/ingress 做白名单 → 转发后即默认信任）

ingress 配置见 forge-deploy/helm/values.yaml::ingress.tls + nginx 配置。
"""
from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

# 仅守 verifier 端点；admin 走 cookie 不需要 mTLS
_PROTECTED_PREFIXES = ("/api/v1/licenses/",)


class MtlsGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        state = getattr(request.app.state, "forge_state", None)
        if state is None or not state.settings.verifier_api_require_mtls:
            return await call_next(request)
        path = request.url.path
        if not any(path.startswith(p) for p in _PROTECTED_PREFIXES):
            return await call_next(request)
        verify_header = request.headers.get("x-ssl-client-verify", "").upper()
        if verify_header != "SUCCESS":
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "client certificate required",
                    "code": "MTLS_REQUIRED",
                },
            )
        return await call_next(request)
