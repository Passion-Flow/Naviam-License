"""DELETE /api/v1/customers/{customer_id} —— 归档客户（软删除）。

不真正删除——把 status 改成 archived，保留 license/api_key FK 引用完整性。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.customers._schema import CustomerResponse
from app.core.audit import ACTION_CUSTOMER_ARCHIVED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories import CustomerRepository
from app.state import AppState, get_state

router = APIRouter()


@router.delete("/{customer_id}", response_model=CustomerResponse)
async def archive_customer(
    customer_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> CustomerResponse:
    if state.customer_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="customer backend not configured",
        )
    repo: CustomerRepository = state.customer_repository  # type: ignore[assignment]

    model = await repo.archive(customer_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer not found")

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_CUSTOMER_ARCHIVED,
        target_type="customer",
        target_id=model.id,
        payload={"slug": model.slug},
    )
    return CustomerResponse.from_model(model)
