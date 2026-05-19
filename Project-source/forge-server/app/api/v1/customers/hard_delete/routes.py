"""POST /api/v1/customers/{customer_id}/hard-delete —— 硬删除客户（数据库直删）。

与 DELETE /customers/{id}（归档）区别：
- archive：status='archived'，保留所有 license / api_key 引用
- hard-delete：真的把客户行从数据库里 DELETE 掉，并级联删除该客户名下所有
  license / api_key / heartbeat / nonce / revocation 条目。不可恢复。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.audit import ACTION_CUSTOMER_DELETED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories import CustomerRepository
from app.state import AppState, get_state

router = APIRouter()


class HardDeleteResponse(BaseModel):
    customer_id: str
    cascaded: dict


@router.post("/{customer_id}/hard-delete", response_model=HardDeleteResponse)
async def hard_delete_customer(
    customer_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> HardDeleteResponse:
    if state.customer_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="customer backend not configured",
        )
    repo: CustomerRepository = state.customer_repository  # type: ignore[assignment]
    result = await repo.hard_delete(customer_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer not found")

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_CUSTOMER_DELETED,
        target_type="customer",
        target_id=customer_id,
        payload={"slug": result["slug"], **result["cascaded"]},
    )
    return HardDeleteResponse(customer_id=customer_id, cascaded=result["cascaded"])
