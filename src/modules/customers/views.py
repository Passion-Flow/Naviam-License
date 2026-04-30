"""Customer CRUD views.

V1：超管可读写；后续开放只读给运营。
"""
from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from modules.accounts.permissions import IsSuperAdmin
from modules.audit.services import append_event
from modules.security.signing import get_audit_signer

from .models import Customer
from .serializers import CustomerSerializer


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def perform_create(self, serializer):
        customer = serializer.save()
        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(self.request.user.id),
            actor_name=self.request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(self.request),
            action="customer.create",
            target_kind="customer",
            target_id=str(customer.id),
            payload={"display_name": customer.display_name},
            signer=audit_signer,
        )
        return customer

    def perform_update(self, serializer):
        customer = serializer.save()
        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(self.request.user.id),
            actor_name=self.request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(self.request),
            action="customer.update",
            target_kind="customer",
            target_id=str(customer.id),
            payload={"display_name": customer.display_name},
            signer=audit_signer,
        )
        return customer

    def perform_destroy(self, instance):
        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(self.request.user.id),
            actor_name=self.request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(self.request),
            action="customer.delete",
            target_kind="customer",
            target_id=str(instance.id),
            payload={"display_name": instance.display_name},
            signer=audit_signer,
        )
        instance.delete()
