"""Product views.

V1：list/retrieve 对登录用户开放；write 仅超管。
"""
from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from modules.accounts.permissions import IsSuperAdmin
from modules.audit.services import append_event
from modules.security.signing import get_audit_signer

from .models import Product
from .serializers import ProductSerializer


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsSuperAdmin()]

    def perform_create(self, serializer):
        product = serializer.save()
        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(self.request.user.id),
            actor_name=self.request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(self.request),
            action="product.create",
            target_kind="product",
            target_id=str(product.id),
            payload={"code": product.code, "display_name": product.display_name},
            signer=audit_signer,
        )
        return product

    def perform_update(self, serializer):
        product = serializer.save()
        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(self.request.user.id),
            actor_name=self.request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(self.request),
            action="product.update",
            target_kind="product",
            target_id=str(product.id),
            payload={"code": product.code, "display_name": product.display_name},
            signer=audit_signer,
        )
        return product

    def perform_destroy(self, instance):
        audit_signer = get_audit_signer()
        append_event(
            actor_id=str(self.request.user.id),
            actor_name=self.request.user.username,
            actor_kind="user",
            actor_ip=_client_ip(self.request),
            action="product.delete",
            target_kind="product",
            target_id=str(instance.id),
            payload={"code": instance.code, "display_name": instance.display_name},
            signer=audit_signer,
        )
        instance.delete()
