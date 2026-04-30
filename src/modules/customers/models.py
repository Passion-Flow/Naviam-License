"""Customer model."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=255, unique=True)
    legal_name = models.CharField(max_length=255, null=True, blank=True)
    contact_name = models.CharField(max_length=128, null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    contact_phone = models.CharField(max_length=64, null=True, blank=True)
    region = models.CharField(max_length=64, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customers_customer"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.display_name
