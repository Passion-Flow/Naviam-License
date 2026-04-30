"""License views.

端点：
- GET/POST   /v1/licenses/            list / issue
- GET/PATCH  /v1/licenses/{id}/       retrieve / partial update notes
- POST       /v1/licenses/{id}/renew/ 续期
- POST       /v1/licenses/{id}/revoke/ 吊销
"""
from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from modules.accounts.permissions import IsSuperAdmin
from modules.audit.services import append_event
from modules.security.signing import get_audit_signer, get_signer

from .models import License
from .serializers import (
    IssueLicenseSerializer,
    LicenseSerializer,
    RenewLicenseSerializer,
    RevokeLicenseSerializer,
)
from .services import issue_license, renew_license, revoke_license


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LicenseViewSet(viewsets.ModelViewSet):
    queryset = License.objects.select_related("product", "customer").all()
    serializer_class = LicenseSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    lookup_field = "id"

    def create(self, request, *args, **kwargs):
        ser = IssueLicenseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        signer = get_signer()
        license_obj, activation_code = issue_license(
            product=data["product"],
            customer=data["customer"],
            cloud_id_text=data["cloud_id_text"],
            expires_at=data["expires_at"],
            issued_by=request.user,
            signer=signer,
            notes=data.get("notes", ""),
            not_before=data.get("not_before"),
            grace_seconds=data.get("grace_seconds", 30 * 24 * 3600),
        )

        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(request.user.id),
            actor_name=request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(request),
            action="license.issue",
            target_kind="license",
            target_id=str(license_obj.id),
            payload={
                "license_id": license_obj.license_id,
                "product_code": license_obj.product.code,
                "customer_id": str(license_obj.customer.id),
            },
            signer=audit_signer,
        )

        return Response(
            {
                "license": LicenseSerializer(license_obj).data,
                "activation_code": activation_code,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="renew")
    def renew(self, request, id=None):
        license_obj = self.get_object()
        ser = RenewLicenseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        signer = get_signer()
        activation_code = renew_license(
            license_obj,
            new_expires_at=ser.validated_data["expires_at"],
            signer=signer,
            grace_seconds=ser.validated_data.get("grace_seconds", 30 * 24 * 3600),
        )

        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(request.user.id),
            actor_name=request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(request),
            action="license.renew",
            target_kind="license",
            target_id=str(license_obj.id),
            payload={
                "license_id": license_obj.license_id,
                "new_expires_at": ser.validated_data["expires_at"].isoformat(),
            },
            signer=audit_signer,
        )

        return Response(
            {
                "license": LicenseSerializer(license_obj).data,
                "activation_code": activation_code,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, id=None):
        license_obj = self.get_object()
        ser = RevokeLicenseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        revoke_license(
            license_obj,
            reason=ser.validated_data["reason"],
            by_user=request.user,
        )

        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(request.user.id),
            actor_name=request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(request),
            action="license.revoke",
            target_kind="license",
            target_id=str(license_obj.id),
            payload={
                "license_id": license_obj.license_id,
                "reason": ser.validated_data["reason"],
            },
            signer=audit_signer,
        )

        return Response(
            {"license": LicenseSerializer(license_obj).data},
            status=status.HTTP_200_OK,
        )
