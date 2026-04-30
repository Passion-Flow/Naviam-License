"""Activation models: CloudId + Heartbeat."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class CloudId(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    license = models.ForeignKey(
        "licenses.License",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="license_id",
    )
    product_code = models.CharField(max_length=64)
    instance_id = models.CharField(max_length=128)
    pubkey_fp = models.CharField(max_length=128)
    hardware_fp = models.CharField(max_length=128)
    schema_version = models.IntegerField()
    raw_text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "activations_cloud_id"
        unique_together = [("product_code", "instance_id", "hardware_fp")]
        indexes = [
            models.Index(fields=["product_code", "instance_id", "hardware_fp"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_code}:{self.instance_id}"


class Heartbeat(models.Model):
    id = models.BigAutoField(primary_key=True)
    license = models.ForeignKey(
        "licenses.License",
        on_delete=models.CASCADE,
        db_column="license_id",
    )
    reported_at = models.DateTimeField()
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    client_version = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=[
            ("ok", "ok"),
            ("mismatch", "mismatch"),
            ("expired", "expired"),
            ("revoked", "revoked"),
        ],
    )
    detail = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "activations_heartbeat"
        indexes = [
            models.Index(fields=["license", "-reported_at"]),
        ]
