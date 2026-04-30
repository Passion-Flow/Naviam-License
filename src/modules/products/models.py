"""Product model.

V1 仅一条种子记录 'default'；后续通过 fixtures 或 admin 添加新产品。
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    schema_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products_product"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.display_name
