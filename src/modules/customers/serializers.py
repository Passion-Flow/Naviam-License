"""Customer serializers."""
from __future__ import annotations

from rest_framework import serializers

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id",
            "display_name",
            "legal_name",
            "contact_name",
            "contact_email",
            "contact_phone",
            "region",
            "notes",
            "created_at",
            "updated_at",
        ]
