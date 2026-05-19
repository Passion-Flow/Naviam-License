"""GET /api/v1/customers/{customer_id} —— 客户详情。仅 Admin Session。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.customers._schema import CustomerResponse
from app.middleware.dual_auth import require_admin_session
from app.repositories import CustomerRepository
from app.state import AppState, get_state

router = APIRouter()


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
) -> CustomerResponse:
    if state.customer_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="customer backend not configured",
        )
    repo: CustomerRepository = state.customer_repository  # type: ignore[assignment]
    model = await repo.get(customer_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer not found")
    return CustomerResponse.from_model(model)
