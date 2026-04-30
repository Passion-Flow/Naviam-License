from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import path

from .signing import get_audit_signer, get_signer


def readiness(request):
    checks: dict[str, bool] = {
        "database": False,
        "cache": False,
        "signing_key": False,
        "audit_key": False,
    }
    status_code = 200

    try:
        connection.ensure_connection()
        checks["database"] = True
    except Exception:
        status_code = 503

    try:
        cache.get("__readyz__")
        checks["cache"] = True
    except Exception:
        status_code = 503

    try:
        get_signer().kid()
        checks["signing_key"] = True
    except Exception:
        status_code = 503

    try:
        get_audit_signer().kid()
        checks["audit_key"] = True
    except Exception:
        status_code = 503

    return JsonResponse(
        {"status": "ok" if status_code == 200 else "degraded", "checks": checks},
        status=status_code,
    )


urlpatterns = [path("", readiness, name="readiness")]
