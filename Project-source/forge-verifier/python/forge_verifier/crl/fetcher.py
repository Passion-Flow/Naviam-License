"""CRL HTTP 拉取 + 本地缓存。

行为：
1. GET <base_url>/api/v1/revocation-list/<algorithm>.crl
2. 用内置公钥验签 + 检查 next_update_at 未过期
3. 比较 sequence 与本地缓存；新 ≥ 旧 才覆盖（防止旧 CRL 回退攻击）
4. 写入 <state_dir>/crl/<algorithm>.crl

返回 CrlFile 或 None（如服务端 404 / 网络错且本地无缓存）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from forge_verifier.crl.parsing import unpack_crl
from forge_verifier.crl.verifier import (
    CrlExpired,
    CrlInvalid,
    CrlVerificationError,
    verify_and_load_crl,
)


@dataclass(frozen=True, slots=True)
class FetchResult:
    """CRL 拉取结果。"""

    fetched_new: bool             # 是否从服务端拿到了新版（已写入缓存）
    crl_path: Path | None         # 当前生效的 CRL 文件路径（缓存 or 新拉）
    sequence: int | None
    reason: str | None = None     # 出错或跳过原因


class CrlFetcher:
    """拉 CRL 的 helper。"""

    def __init__(
        self,
        *,
        base_url: str,
        algorithm: str,
        public_key: bytes,
        cache_dir: Path,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._algorithm = algorithm
        self._public_key = public_key
        self._cache_dir = Path(cache_dir)
        self._timeout = timeout_seconds

    def _cache_path(self) -> Path:
        return self._cache_dir / "crl" / f"{self._algorithm}.crl"

    def _read_cached_sequence(self) -> int | None:
        cache_path = self._cache_path()
        if not cache_path.exists():
            return None
        try:
            cached = unpack_crl(cache_path.read_bytes())
            return cached.payload.sequence
        except Exception:
            return None

    async def fetch(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        now: datetime | None = None,
    ) -> FetchResult:
        """拉取并落盘。"""
        url = f"{self._base_url}/api/v1/revocation-list/{self._algorithm}.crl"

        async def _do(c: httpx.AsyncClient) -> httpx.Response:
            return await c.get(url, timeout=self._timeout)

        try:
            if client is not None:
                response = await _do(client)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    response = await _do(c)
        except httpx.HTTPError as exc:
            return FetchResult(
                fetched_new=False,
                crl_path=self._cache_path() if self._cache_path().exists() else None,
                sequence=self._read_cached_sequence(),
                reason=f"network error: {exc}",
            )

        if response.status_code != 200:
            return FetchResult(
                fetched_new=False,
                crl_path=self._cache_path() if self._cache_path().exists() else None,
                sequence=self._read_cached_sequence(),
                reason=f"http {response.status_code}",
            )

        # 验签 + 过期检查
        try:
            crl = verify_and_load_crl(crl_bytes=response.content, public_key=self._public_key, now=now)
        except (CrlInvalid, CrlExpired, CrlVerificationError) as exc:
            return FetchResult(
                fetched_new=False,
                crl_path=self._cache_path() if self._cache_path().exists() else None,
                sequence=self._read_cached_sequence(),
                reason=f"invalid crl: {exc}",
            )

        # 序号回退防护
        cached_seq = self._read_cached_sequence()
        if cached_seq is not None and crl.payload.sequence < cached_seq:
            return FetchResult(
                fetched_new=False,
                crl_path=self._cache_path(),
                sequence=cached_seq,
                reason=(
                    f"received sequence={crl.payload.sequence} < cached={cached_seq}; "
                    f"refusing to roll back"
                ),
            )

        # 写入缓存
        cache_path = self._cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp.write_bytes(response.content)
        tmp.replace(cache_path)
        try:
            cache_path.chmod(0o600)
        except OSError:
            pass

        return FetchResult(
            fetched_new=True,
            crl_path=cache_path,
            sequence=crl.payload.sequence,
        )
