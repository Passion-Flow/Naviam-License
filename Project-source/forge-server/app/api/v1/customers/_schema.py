"""Customer 资源共享响应 Schema —— 单一资源内部复用，跨资源不共享。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.customer import CustomerModel


class CustomerResponse(BaseModel):
    id: str
    slug: str
    name: str
    contact_email: str
    contact_name: str
    region: str
    status: str
    notes: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m: CustomerModel) -> "CustomerResponse":
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            contact_email=m.contact_email,
            contact_name=m.contact_name,
            region=m.region,
            status=m.status,
            notes=m.notes,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
