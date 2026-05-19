"""GET /api/v1/products/{product_id} —— 产品详情。仅 Admin Session。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.products._schema import ProductResponse
from app.middleware.dual_auth import require_admin_session
from app.repositories import ProductRepository
from app.state import AppState, get_state

router = APIRouter()


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
) -> ProductResponse:
    if state.product_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="product backend not configured",
        )
    repo: ProductRepository = state.product_repository  # type: ignore[assignment]
    model = await repo.get(product_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return ProductResponse.from_model(model)
