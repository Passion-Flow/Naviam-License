"""Pagination protocol shared across list endpoints."""
from __future__ import annotations

from typing import Generic, TypeVar

from rest_framework.pagination import PageNumberPagination

T = TypeVar("T")


class LicensePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


# Documentation-oriented type stubs; runtime not used.
class Pagination(Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
