from __future__ import annotations

from functools import lru_cache

from .settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
