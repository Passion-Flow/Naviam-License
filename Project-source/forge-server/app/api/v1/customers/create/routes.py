"""POST /api/v1/customers —— 新建客户。仅 Admin Session。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.customers._schema import CustomerResponse
from app.core.audit import ACTION_CUSTOMER_CREATED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories import CustomerRepository, CustomerSlugConflict
from app.state import AppState, get_state

router = APIRouter()


class CreateCustomerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    contact_email: str = Field(default="", max_length=256)
    contact_name: str = Field(default="", max_length=128)
    region: str = Field(default="", max_length=64)
    notes: str = Field(default="", max_length=10_000)


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CreateCustomerBody,
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
    try:
        model = await repo.create(
            slug=body.slug,
            name=body.name,
            contact_email=body.contact_email,
            contact_name=body.contact_name,
            region=body.region,
            notes=body.notes,
        )
    except CustomerSlugConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"customer slug already exists: {body.slug}",
        ) from exc

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_CUSTOMER_CREATED,
        target_type="customer",
        target_id=model.id,
        payload={"slug": model.slug, "name": model.name},
    )
    return CustomerResponse.from_model(model)
