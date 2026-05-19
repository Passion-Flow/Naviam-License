"""Admin user response schema —— never returns password hash."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.user import UserModel


class AdminUserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_super: bool
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m: UserModel) -> "AdminUserResponse":
        return cls(
            id=m.id,
            username=m.username,
            email=m.email,
            is_super=m.is_super,
            is_active=m.is_active,
            last_login_at=m.last_login_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
