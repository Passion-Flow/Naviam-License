"""Errors / response codes shared across modules."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LicenseAPIError(Exception):
    code: str
    message: str
    http_status: int = 400
    hint: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            **({"hint": self.hint} if self.hint else {}),
        }
