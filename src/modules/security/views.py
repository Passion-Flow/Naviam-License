from __future__ import annotations

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


def _password_min_length() -> int:
    for validator in settings.AUTH_PASSWORD_VALIDATORS:
        if validator.get("NAME", "").endswith("MinimumLengthValidator"):
            return int(validator.get("OPTIONS", {}).get("min_length", 8))
    return 8


def _password_hasher_label() -> str:
    first_hasher = settings.PASSWORD_HASHERS[0].rsplit(".", 1)[-1]
    if first_hasher == "Argon2PasswordHasher":
        return "Argon2id"
    return first_hasher.replace("PasswordHasher", "")


def _lockout_minutes() -> int:
    return round(float(settings.AXES_COOLOFF_TIME) * 60)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def security_settings_view(request):
    throttle_rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
    return Response(
        {
            "password": {
                "hasher": _password_hasher_label(),
                "min_length": _password_min_length(),
                "can_change": True,
            },
            "totp": {
                "enabled": bool(request.user.totp_confirmed),
                "can_setup": True,
                "can_disable": bool(request.user.totp_confirmed),
                "issuer": settings.APP_NAME,
            },
            "session": {
                "duration_hours": round(settings.SESSION_COOKIE_AGE / 3600),
                "lockout_limit": settings.AXES_FAILURE_LIMIT,
                "lockout_minutes": _lockout_minutes(),
                "user_rate_limit": throttle_rates.get("user", ""),
                "csrf_enabled": True,
                "csrf_same_site": settings.CSRF_COOKIE_SAMESITE,
            },
            "signing": {
                "algorithm": "Ed25519",
                "kid": settings.SIGNING_KEY_KID,
                "backend": settings.SIGNING_KEY_BACKEND,
                "audit_enabled": True,
                "audit_kid": settings.AUDIT_KEY_KID,
            },
        }
    )
