"""POST /api/v1/licenses/{license_id}/heartbeat — Verifier 心跳上报。

Header: X-Forge-API-Key: <plaintext>
Body:   HeartbeatRequest（含 HMAC signature）

服务端逻辑：
1. API Key 鉴权（require_api_key）
2. 校验请求体 HMAC（用 API Key 明文做 HMAC key）
3. 校验时钟漂移、防重放（nonce 短 TTL cache）
4. 记录心跳到 collector
5. 触发 multi-env detector，返回 anomaly 标志
6. 查吊销列表，告知 license_status
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.core.license.heartbeat import (
    HeartbeatRecord,
    HeartbeatRequest,
    HeartbeatResponse,
    HeartbeatVerificationError,
    verify_request,
)
from app.middleware.api_key_auth import require_api_key
from app.state import AppState, ApiKeyInfo, get_state

router = APIRouter()


@router.post("/{license_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat_endpoint(
    body: HeartbeatRequest,
    license_id: str = Path(),
    auth: tuple[ApiKeyInfo, str] = Depends(require_api_key),
    state: AppState = Depends(get_state),
) -> HeartbeatResponse:
    api_key_info, plaintext_key = auth

    # 路径里的 license_id 必须与 body 中一致（防止替换攻击）
    if body.license_id != license_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="license_id mismatch between path and body",
        )

    now_utc = datetime.now(timezone.utc)

    # nonce 防重放
    seen = await state.heartbeat_collector.is_nonce_seen(license_id, body.nonce)

    try:
        verify_request(body, api_key=plaintext_key, now=now_utc, seen_nonce=seen)
    except HeartbeatVerificationError as exc:
        # 401 而非 400 — 这是认证类失败
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    # 标记 nonce 已见
    await state.heartbeat_collector.mark_nonce_seen(license_id, body.nonce)

    # 入库
    await state.heartbeat_collector.record(
        HeartbeatRecord(
            license_id=license_id,
            fingerprint=body.fingerprint,
            received_at=now_utc,
            reported_at=body.reported_at,
            nonce=body.nonce,
            api_key_id=api_key_info.key_id,
            verifier_version=body.verifier_version,
        )
    )

    # 触发多环境检测
    verdict = await state.multi_env_detector.evaluate(
        license_id, collector=state.heartbeat_collector, now=now_utc,
    )

    # 异常时记审计 + 推 webhook（best-effort）
    if verdict.anomaly:
        from app.core.audit import ACTOR_API_KEY, record_audit
        from app.core.webhooks import emit_event
        anomaly_payload = {
            "license_id": license_id,
            "api_key_id": api_key_info.key_id,
            "fingerprint": body.fingerprint,
            "detected_at": now_utc.isoformat(),
        }
        if state.audit_log_repository is not None:
            await state.audit_log_repository.record(  # type: ignore[union-attr]
                actor_type=ACTOR_API_KEY,
                actor_id=api_key_info.key_id,
                action="heartbeat.anomaly_detected",
                target_type="license",
                target_id=license_id,
                payload=anomaly_payload,
            )
        await emit_event("heartbeat.anomaly_detected", anomaly_payload)

    # 查吊销列表（in-memory store —— 真实场景从 DB）
    revocation_entries = await state.revocation_store.list_entries()
    revoked = any(e.license_id == license_id for e in revocation_entries)
    license_status = "revoked" if revoked else "valid"

    return HeartbeatResponse(
        license_status=license_status,
        multi_env_anomaly=verdict.anomaly,
        next_heartbeat_after_seconds=state.settings.heartbeat_default_interval_seconds,
        server_time=now_utc,
    )
