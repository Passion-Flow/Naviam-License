"""GET /api/v1/customers —— 列出客户。仅 Admin Session。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.customers._schema import CustomerResponse
from app.middleware.dual_auth import require_admin_session
from app.repositories import CustomerRepository
from app.state import AppState, get_state

router = APIRouter()


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    limit: int
    offset: int


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CustomerListResponse:
    if state.customer_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="customer backend not configured",
        )
    repo: CustomerRepository = state.customer_repository  # type: ignore[assignment]
    rows = await repo.list(status=status_filter, limit=limit, offset=offset)
    return CustomerListResponse(
        items=[CustomerResponse.from_model(r) for r in rows],
        limit=limit,
        offset=offset,
    )
