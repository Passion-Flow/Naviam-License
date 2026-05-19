"""DELETE /api/v1/products/{product_id} —— 硬删除产品（数据库直删）。

级联：删除该产品名下所有 license / heartbeat / nonce / revocation。不可恢复。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.audit import ACTION_PRODUCT_DELETED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories import ProductRepository
from app.state import AppState, get_state

router = APIRouter()


class DeleteProductResponse(BaseModel):
    product_id: str
    cascaded: dict


@router.delete("/{product_id}", response_model=DeleteProductResponse)
async def hard_delete_product(
    product_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> DeleteProductResponse:
    if state.product_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="product backend not configured",
        )
    repo: ProductRepository = state.product_repository  # type: ignore[assignment]
    result = await repo.hard_delete(product_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_PRODUCT_DELETED,
        target_type="product",
        target_id=product_id,
        payload={"slug": result["slug"], **result["cascaded"]},
    )
    return DeleteProductResponse(product_id=product_id, cascaded=result["cascaded"])
