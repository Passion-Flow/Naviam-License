"""DRF exception handler.

阶段 2 实现：
- LicenseAPIError -> 结构化 JSON 响应。
- 其它异常 -> 统一 500 + trace_id；生产环境不暴露堆栈。
"""
from __future__ import annotations

import secrets
import traceback
from typing import Any

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default

from contracts.errors import LicenseAPIError


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    request = context.get("request")

    if isinstance(exc, LicenseAPIError):
        return Response(
            {
                "error": exc.to_payload(),
                "trace_id": _trace_id(request),
            },
            status=exc.http_status,
        )

    resp = drf_default(exc, context)
    if resp is not None:
        # DRF 已知的异常（ValidationError / AuthenticationFailed 等）
        resp.data = {
            "error": resp.data,
            "trace_id": _trace_id(request),
        }
        return resp

    # 未捕获异常
    trace_id = _trace_id(request)
    if settings.DEBUG:
        detail = traceback.format_exc()
    else:
        detail = "internal server error"

    return Response(
        {
            "error": {"detail": detail, "code": "internal_error"},
            "trace_id": trace_id,
        },
        status=500,
    )


def _trace_id(request: Any) -> str:
    # 优先复用前端传入的 trace_id；否则生成新的
    if request and hasattr(request, "META"):
        tid = request.META.get("HTTP_X_TRACE_ID")
        if tid:
            return str(tid)
    return secrets.token_hex(8)
