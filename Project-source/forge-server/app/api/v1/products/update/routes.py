"""PATCH /api/v1/products/{product_id} —— 更新产品定义（不可改 slug）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.products._schema import ProductResponse
from app.core.audit import ACTION_PRODUCT_UPDATED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories import ProductRepository
from app.state import AppState, get_state

router = APIRouter()


class UpdateProductBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=10_000)
    version: str | None = Field(default=None, max_length=32)
    features_schema: dict | None = None
    default_limits: dict | None = None
    status: str | None = Field(default=None, pattern=r"^(active|archived)$")


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    body: UpdateProductBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> ProductResponse:
    if state.product_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="product backend not configured",
        )
    repo: ProductRepository = state.product_repository  # type: ignore[assignment]

    fields = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not fields:
        existing = await repo.get(product_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
        return ProductResponse.from_model(existing)

    model = await repo.update(product_id, fields=fields)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_PRODUCT_UPDATED,
        target_type="product",
        target_id=model.id,
        payload={"updated_fields": list(fields.keys())},
    )
    return ProductResponse.from_model(model)
