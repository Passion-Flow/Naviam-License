"""GET /api/v1/products —— 列出产品。仅 Admin Session。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.products._schema import ProductResponse
from app.middleware.dual_auth import require_admin_session
from app.repositories import ProductRepository
from app.state import AppState, get_state

router = APIRouter()


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    limit: int
    offset: int


@router.get("", response_model=ProductListResponse)
async def list_products(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductListResponse:
    if state.product_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="product backend not configured",
        )
    repo: ProductRepository = state.product_repository  # type: ignore[assignment]
    rows = await repo.list(status=status_filter, limit=limit, offset=offset)
    return ProductListResponse(
        items=[ProductResponse.from_model(r) for r in rows],
        limit=limit,
        offset=offset,
    )
