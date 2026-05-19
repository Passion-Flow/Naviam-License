"""Product 资源共享响应 Schema —— 单一资源内部复用。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.product import ProductModel


class ProductResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    version: str
    features_schema: dict
    default_limits: dict
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m: ProductModel) -> "ProductResponse":
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            description=m.description,
            version=m.version,
            features_schema=m.features_schema or {},
            default_limits=m.default_limits or {},
            status=m.status,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
