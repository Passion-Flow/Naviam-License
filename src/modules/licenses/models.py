"""License model with state machine."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class License(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_GRACE = "grace"
    STATUS_REVOKED = "revoked"
    STATUS_SUNSET = "sunset"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "draft"),
        (STATUS_ISSUED, "issued"),
        (STATUS_ACTIVE, "active"),
        (STATUS_EXPIRED, "expired"),
        (STATUS_GRACE, "grace"),
        (STATUS_REVOKED, "revoked"),
        (STATUS_SUNSET, "sunset"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    license_id = models.CharField(max_length=64, unique=True)
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        db_column="product_id",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        db_column="customer_id",
    )
    cloud_id_binding = models.BinaryField()
    cloud_id_text = models.TextField()
    hardware_fp_hash = models.BinaryField()
    instance_pubkey = models.BinaryField()
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    not_before = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    grace_until = models.DateTimeField(null=True, blank=True)
    signature = models.BinaryField(null=True, blank=True)
    signature_algo = models.CharField(max_length=32, default="ed25519")
    signature_kid = models.CharField(max_length=64, default="")
    payload_canonical = models.BinaryField()
    notes = models.TextField(null=True, blank=True)
    issued_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        db_column="issued_by",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "licenses_license"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["product", "status"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["license_id"]),
        ]

    def __str__(self) -> str:
        return self.license_id

    def compute_status(self, now: timezone.datetime | None = None) -> str:
        """根据当前时间计算应有的状态。"""
        now = now or timezone.now()
        if self.status == self.STATUS_REVOKED:
            return self.STATUS_REVOKED
        if self.status == self.STATUS_SUNSET:
            return self.STATUS_SUNSET
        if now < self.not_before:
            return self.STATUS_DRAFT if self.status == self.STATUS_DRAFT else self.STATUS_ISSUED
        if now <= self.expires_at:
            return self.STATUS_ACTIVE if self.status in (self.STATUS_ACTIVE, self.STATUS_ISSUED) else self.status
        if self.grace_until and now <= self.grace_until:
            return self.STATUS_GRACE
        return self.STATUS_SUNSET
