"""Audit hash chain model."""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    prev_hash = models.BinaryField()
    hash = models.BinaryField(unique=True)
    signature = models.BinaryField()
    signature_kid = models.CharField(max_length=64)
    ts = models.DateTimeField(default=timezone.now)
    actor_id = models.UUIDField(null=True, blank=True)
    actor_name = models.CharField(max_length=255, null=True, blank=True)
    actor_kind = models.CharField(max_length=32)
    actor_ip = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=64)
    target_kind = models.CharField(max_length=32, null=True, blank=True)
    target_id = models.CharField(max_length=128, null=True, blank=True)
    request_id = models.CharField(max_length=64, null=True, blank=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "audit_event"
        ordering = ["-ts"]
        indexes = [
            models.Index(fields=["-ts"]),
            models.Index(fields=["action", "-ts"]),
        ]
