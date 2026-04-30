"""License serializers."""
from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from modules.customers.models import Customer
from modules.products.models import Product

from .models import License


class LicenseSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="product.code", read_only=True)
    customer_name = serializers.CharField(source="customer.display_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = License
        fields = [
            "id",
            "license_id",
            "product_code",
            "customer_name",
            "cloud_id_text",
            "status",
            "status_display",
            "issued_at",
            "not_before",
            "expires_at",
            "grace_until",
            "signature_kid",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class IssueLicenseSerializer(serializers.Serializer):
    cloud_id_text = serializers.CharField(required=True, trim_whitespace=False)
    customer_id = serializers.UUIDField(required=True)
    product_id = serializers.UUIDField(required=True)
    expires_at = serializers.DateTimeField(required=True)
    not_before = serializers.DateTimeField(required=False, allow_null=True)
    grace_seconds = serializers.IntegerField(required=False, default=30 * 24 * 3600, min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_expires_at(self, value: timezone.datetime) -> timezone.datetime:
        if value <= timezone.now():
            raise serializers.ValidationError("expires_at must be in the future")
        return value

    def validate(self, attrs: dict) -> dict:
        try:
            attrs["customer"] = Customer.objects.get(id=attrs["customer_id"])
        except Customer.DoesNotExist:
            raise serializers.ValidationError({"customer_id": "not found"})
        try:
            attrs["product"] = Product.objects.get(id=attrs["product_id"])
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id": "not found"})
        return attrs


class RenewLicenseSerializer(serializers.Serializer):
    expires_at = serializers.DateTimeField(required=True)
    grace_seconds = serializers.IntegerField(required=False, default=30 * 24 * 3600, min_value=0)

    def validate_expires_at(self, value: timezone.datetime) -> timezone.datetime:
        if value <= timezone.now():
            raise serializers.ValidationError("expires_at must be in the future")
        return value


class RevokeLicenseSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=1024)
