"""Notification serializers."""
from __future__ import annotations

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "category",
            "title",
            "message",
            "is_read",
            "action_url",
            "created_at",
        ]
        read_only_fields = fields
