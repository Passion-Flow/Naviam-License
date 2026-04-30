"""Notification model for user in-app notifications."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class Notification(models.Model):
    CATEGORY_CHOICES = [
        ("license", "License"),
        ("customer", "Customer"),
        ("product", "Product"),
        ("system", "System"),
        ("security", "Security"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default="system")
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    action_url = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]
