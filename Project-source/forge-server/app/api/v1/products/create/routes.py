"""POST /api/v1/products —— 新建产品定义。仅 Admin Session。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.products._schema import ProductResponse
from app.core.audit import ACTION_PRODUCT_CREATED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories import ProductRepository, ProductSlugConflict
from app.state import AppState, get_state

router = APIRouter()


class CreateProductBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=10_000)
    version: str = Field(default="", max_length=32)
    features_schema: dict = Field(default_factory=dict)
    default_limits: dict = Field(default_factory=dict)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: CreateProductBody,
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
    try:
        model = await repo.create(
            slug=body.slug,
            name=body.name,
            description=body.description,
            version=body.version,
            features_schema=body.features_schema,
            default_limits=body.default_limits,
        )
    except ProductSlugConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"product slug already exists: {body.slug}",
        ) from exc

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_PRODUCT_CREATED,
        target_type="product",
        target_id=model.id,
        payload={"slug": model.slug, "name": model.name, "version": model.version},
    )
    return ProductResponse.from_model(model)
