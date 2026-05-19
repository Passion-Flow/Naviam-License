"""ApiKeyRepository —— API Key 持久化 + DB-backed 鉴权检查。"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update

from app.adapters.database.interface.protocol import Database
from app.models.api_key import ApiKeyModel
from app.state import ApiKeyInfo


def _hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class ApiKeyRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def issue(
        self,
        *,
        customer_id: str,
        project_label: str,
        expires_at: datetime | None = None,
    ) -> tuple[ApiKeyModel, str]:
        """新建一把 API Key。返回 (model, plaintext)；明文只在签发时返回一次。

        expires_at = None 表示永不过期；非空时必须是 UTC 且严格未来时间（由调用方保证）。
        """
        plaintext = secrets.token_urlsafe(32)
        key_id = secrets.token_hex(12)
        model = ApiKeyModel(
            key_id=key_id,
            key_hash=_hash_api_key(plaintext),
            key_prefix=plaintext[:8],
            customer_id=customer_id,
            project_label=project_label,
            status="active",
            expires_at=expires_at,
        )
        async with self._db.session() as sess:
            sess.add(model)
        return model, plaintext

    async def find_by_plaintext(self, plaintext: str) -> ApiKeyModel | None:
        key_hash = _hash_api_key(plaintext)
        async with self._db.session() as sess:
            stmt = select(ApiKeyModel).where(ApiKeyModel.key_hash == key_hash)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def revoke(self, key_id: str) -> None:
        async with self._db.session() as sess:
            stmt = (
                update(ApiKeyModel)
                .where(ApiKeyModel.key_id == key_id)
                .values(status="revoked", revoked_at=datetime.now(timezone.utc))
            )
            await sess.execute(stmt)

    async def hard_delete(self, key_id: str) -> bool:
        """硬删除 API Key 行。心跳记录中 api_key_id 是可选元数据，置空保留。"""
        from sqlalchemy import delete, update as _update

        from app.models.heartbeat import HeartbeatLogModel

        async with self._db.session() as sess:
            model = await sess.get(ApiKeyModel, key_id)
            if model is None:
                return False
            # 心跳里的 api_key_id 是 nullable 元数据 — 不级联删行，置 None
            await sess.execute(
                _update(HeartbeatLogModel)
                .where(HeartbeatLogModel.api_key_id == key_id)
                .values(api_key_id=None)
            )
            await sess.execute(delete(ApiKeyModel).where(ApiKeyModel.key_id == key_id))
        return True

    async def mark_used(self, key_id: str) -> None:
        async with self._db.session() as sess:
            stmt = (
                update(ApiKeyModel)
                .where(ApiKeyModel.key_id == key_id)
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await sess.execute(stmt)

    async def list_for_customer(self, customer_id: str) -> Sequence[ApiKeyModel]:
        async with self._db.session() as sess:
            stmt = select(ApiKeyModel).where(ApiKeyModel.customer_id == customer_id)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def list_all(
        self,
        *,
        status: str | None = None,
        customer_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ApiKeyModel]:
        async with self._db.session() as sess:
            stmt = select(ApiKeyModel)
            if status is not None:
                stmt = stmt.where(ApiKeyModel.status == status)
            if customer_id is not None:
                stmt = stmt.where(ApiKeyModel.customer_id == customer_id)
            stmt = stmt.order_by(ApiKeyModel.created_at.desc()).limit(limit).offset(offset)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def get(self, key_id: str) -> ApiKeyModel | None:
        async with self._db.session() as sess:
            return await sess.get(ApiKeyModel, key_id)


class DbBackedApiKeyAuth:
    """替换 state.api_keys 字典的查表逻辑，按需查 DB。"""

    def __init__(self, repo: ApiKeyRepository) -> None:
        self._repo = repo

    async def lookup(self, plaintext: str) -> ApiKeyInfo | None:
        model = await self._repo.find_by_plaintext(plaintext)
        if model is None or model.status != "active":
            return None
        # 过期判定 —— DB 不动 status，避免一次 lookup 写一次；纯按时间筛
        if model.expires_at is not None and model.expires_at < datetime.now(timezone.utc):
            return None
        return ApiKeyInfo(
            key_id=model.key_id,
            key_hash=model.key_hash,
            customer_id=model.customer_id,
            project_label=model.project_label,
            status=model.status,
            expires_at=model.expires_at,
        )
