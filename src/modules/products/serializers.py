"""Product serializers."""
from __future__ import annotations

from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id",
            "code",
            "display_name",
            "description",
            "schema_version",
            "created_at",
            "updated_at",
        ]
