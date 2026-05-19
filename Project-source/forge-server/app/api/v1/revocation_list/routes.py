"""GET /api/v1/revocation-list/{algorithm}.crl — 公开 CRL 下载（不鉴权）。

返回 `.crl` 二进制流（application/octet-stream）。
Verifier 在 hybrid/online 模式下定期拉这个，用内置公钥验签后载入本地。

ETag / Cache-Control 协议：
- 响应永远带 `ETag: "<sha256>"`（内容散列，跨进程稳定）
- 响应 `Cache-Control: max-age=<next_update_window/2>, must-revalidate` —— 半个窗口期内
  允许 verifier 直接复用本地缓存而无需回连
- 请求带 `If-None-Match: "<etag>"` 且匹配 → **304 Not Modified**，省传整个 body
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response

from app.state import AppState, get_state

router = APIRouter()


def _etag_match(if_none_match: str | None, etag: str) -> bool:
    """`If-None-Match` 接受 `W/"x"` 弱标记或裸 ETag；规范化后比较。"""
    if not if_none_match:
        return False
    for raw in if_none_match.split(","):
        candidate = raw.strip().lstrip("W/").strip().strip('"')
        if candidate == etag:
            return True
    return False


@router.get("/{algorithm}.crl")
async def get_crl(
    algorithm: str,
    state: AppState = Depends(get_state),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    # 多算法支持：放行 settings.signing_algorithms_enabled 中所有算法。
    # 不在 enabled list → 404（不区分 "无效算法名" / "禁用算法"，避免侧信道）。
    if algorithm not in state.settings.signing_algorithms_enabled:
        return Response(status_code=404)

    hit = await state.crl_manager.build_crl(algorithm=algorithm)
    quoted_etag = f'"{hit.etag}"'
    # next_update_at - signed_at == _next_update_window；取一半做 max-age 让客户端在窗口
    # 中点必须 revalidate，避免使用过期 CRL
    window_seconds = max(int((hit.next_update_at - hit.signed_at).total_seconds()), 1)
    max_age = max(window_seconds // 2, 1)

    common_headers = {
        "ETag": quoted_etag,
        "Cache-Control": f"public, max-age={max_age}, must-revalidate",
    }
    if _etag_match(if_none_match, hit.etag):
        return Response(status_code=304, headers=common_headers)

    return Response(
        content=hit.bytes,
        media_type="application/octet-stream",
        headers={
            **common_headers,
            "Content-Disposition": f'attachment; filename="forge-{algorithm}.crl"',
        },
    )
