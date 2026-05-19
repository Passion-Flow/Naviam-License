"""PATCH /api/v1/customers/{customer_id} —— 更新客户信息（不可改 slug）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.customers._schema import CustomerResponse
from app.core.audit import ACTION_CUSTOMER_UPDATED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories import CustomerRepository
from app.state import AppState, get_state

router = APIRouter()


class UpdateCustomerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    contact_email: str | None = Field(default=None, max_length=256)
    contact_name: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=10_000)
    status: str | None = Field(default=None, pattern=r"^(active|archived)$")


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    body: UpdateCustomerBody,
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

    fields = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not fields:
        # 空 body：直接返回当前快照
        existing = await repo.get(customer_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer not found")
        return CustomerResponse.from_model(existing)

    model = await repo.update(customer_id, fields=fields)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer not found")

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_CUSTOMER_UPDATED,
        target_type="customer",
        target_id=model.id,
        payload={"updated_fields": list(fields.keys())},
    )
    return CustomerResponse.from_model(model)
