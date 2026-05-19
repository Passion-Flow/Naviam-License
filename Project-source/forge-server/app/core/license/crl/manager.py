"""CrlManager — LA 侧的 CRL 生命周期 + RevocationStore 存储抽象。

业务边界：
- `RevocationStore`：吊销项的存取（生产用 DB；测试用 InMemory）
- `CrlManager`：拉取 entries → 构造 payload → 签名 → 打包成 .crl 字节流

序号 `sequence` 由 store 维护，单调递增。
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.core.key_storage import KeyStorage
from app.core.license.crl.format import (
    CRL_FORMAT_VERSION,
    CRL_MAGIC,
    CrlMetadata,
    RevocationEntry,
    RevocationListPayload,
    pack_crl,
)
from app.core.license.issuer.issue_with_storage import find_active_key_id
from app.core.signing import get_signer


@dataclass(frozen=True, slots=True)
class _StoredEntry:
    license_id: str
    revoked_at: datetime
    reason: str


class RevocationStore(Protocol):
    """吊销记录存储统一接口。"""

    async def add(
        self,
        license_id: str,
        *,
        reason: str = "",
        revoked_by: str | None = None,
        now: datetime | None = None,
    ) -> None: ...
    async def remove(self, license_id: str) -> None: ...
    async def exists(self, license_id: str) -> bool: ...
    async def list_entries(self) -> list[RevocationEntry]: ...
    async def next_sequence(self) -> int: ...


class InMemoryRevocationStore(RevocationStore):
    """单元测试 + 单实例降级用。"""

    def __init__(self) -> None:
        self._entries: dict[str, _StoredEntry] = {}
        self._sequence = 0

    async def add(
        self,
        license_id: str,
        *,
        reason: str = "",
        revoked_by: str | None = None,  # in-memory 不存（接口对齐 DB）
        now: datetime | None = None,
    ) -> None:
        ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self._entries[license_id] = _StoredEntry(license_id=license_id, revoked_at=ts, reason=reason)

    async def remove(self, license_id: str) -> None:
        self._entries.pop(license_id, None)

    async def exists(self, license_id: str) -> bool:
        return license_id in self._entries

    async def list_entries(self) -> list[RevocationEntry]:
        return [
            RevocationEntry(license_id=e.license_id, revoked_at=e.revoked_at, reason=e.reason)
            for e in self._entries.values()
        ]

    async def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence


@dataclass(frozen=True, slots=True)
class CrlCacheHit:
    """已经构造好的 CRL，可作为响应直接返回。"""

    bytes: bytes
    etag: str   # sha256 of content; stable across processes
    sequence: int
    signed_at: datetime
    next_update_at: datetime


class CrlManager:
    """生成 / 签名 / 打包 CRL。

    缓存策略：按内容散列复用。同样的 entries 集合不重复签名 / 不重复 bump sequence —— 这让：
    1. 多副本 admin 部署里 ETag 跨进程稳定
    2. KMS 后端不被无谓签名 API 调用淹没
    3. verifier 端能命中 `If-None-Match`，省一半带宽

    sequence 只在内容真实变更时才递增（与"版本号"语义一致）。
    """

    def __init__(
        self,
        *,
        store: RevocationStore,
        key_storage: KeyStorage,
        algorithm: str = "ed25519",
        next_update_window: timedelta = timedelta(hours=24),
    ) -> None:
        self._store = store
        self._key_storage = key_storage
        self._algorithm = algorithm  # 默认算法；可被 build_crl(algorithm=...) 覆盖
        self._next_update_window = next_update_window
        # algorithm → CrlCacheHit。每种算法独立缓存：吊销集相同但签名 / ETag 不同。
        self._cache: dict[str, CrlCacheHit] = {}

    async def revoke(
        self,
        license_id: str,
        *,
        reason: str = "",
        revoked_by: str | None = None,
    ) -> None:
        await self._store.add(license_id, reason=reason, revoked_by=revoked_by)
        self._cache.clear()  # 内容变更：所有算法的缓存一起废弃

    async def unrevoke(self, license_id: str) -> None:
        await self._store.remove(license_id)
        self._cache.clear()

    async def is_revoked(self, license_id: str) -> bool:
        return await self._store.exists(license_id)

    @staticmethod
    def _content_hash(entries: list[RevocationEntry], algorithm: str) -> str:
        """对 (algorithm, sorted entries) 求确定性 SHA-256。

        相同内容 → 相同 hash → 同一份 CRL 可以跨进程 / 重启复用 ETag。
        """
        items = sorted(
            (
                {"license_id": e.license_id, "reason": e.reason, "revoked_at": e.revoked_at.isoformat()}
                for e in entries
            ),
            key=lambda d: d["license_id"],
        )
        digest = hashlib.sha256()
        digest.update(algorithm.encode("ascii"))
        digest.update(b"\x00")
        digest.update(json.dumps(items, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        return digest.hexdigest()

    async def build_crl(
        self,
        *,
        algorithm: str | None = None,
        now: datetime | None = None,
    ) -> CrlCacheHit:
        """构造（或复用）当前算法对应的 CRL。

        `algorithm=None` → 用构造时的默认；显式传入支持多算法并行（信创场景一份
        ed25519 给海外、一份 sm2 给信创客户）。每个算法各自有 sequence 与签名密钥。

        - 第一次调用某算法：list_entries → next_sequence → sign → pack → cache
        - 后续调用且内容未变：跳过 next_sequence 与 sign，直接返回缓存
        - 内容变化（新增/删除 entry）：所有算法缓存一起 invalidate
        """
        algo = algorithm or self._algorithm
        now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        entries = await self._store.list_entries()
        content_hash = self._content_hash(entries, algo)

        cached = self._cache.get(algo)
        if cached is not None and cached.etag == content_hash:
            return cached

        sequence = await self._store.next_sequence()
        next_update_at = now_utc + self._next_update_window
        payload = RevocationListPayload(
            crl_version=CRL_FORMAT_VERSION,
            sequence=sequence,
            issued_at=now_utc,
            next_update_at=next_update_at,
            entries=entries,
        )

        key_id = await find_active_key_id(self._key_storage, algo)
        record = await self._key_storage.load(key_id)
        signer = get_signer(algo)
        sig = signer.sign(
            private_key=record.private_key,
            key_id=record.key_id,
            payload=payload.canonical_bytes(),
        )

        metadata = CrlMetadata(
            magic=CRL_MAGIC,
            crl_format_version=CRL_FORMAT_VERSION,
            algorithm=algo,
            key_id=record.key_id,
            signed_at=now_utc,
        )
        crl_bytes = pack_crl(payload, sig.signature, metadata)
        hit = CrlCacheHit(
            bytes=crl_bytes,
            etag=content_hash,
            sequence=sequence,
            signed_at=now_utc,
            next_update_at=next_update_at,
        )
        self._cache[algo] = hit
        return hit

    async def generate_crl(
        self,
        *,
        algorithm: str | None = None,
        now: datetime | None = None,
    ) -> bytes:
        """向后兼容入口；新代码应直接走 `build_crl()` 拿 ETag / metadata。"""
        hit = await self.build_crl(algorithm=algorithm, now=now)
        return hit.bytes
