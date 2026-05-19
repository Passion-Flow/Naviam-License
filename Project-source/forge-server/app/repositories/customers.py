"""CustomerRepository —— 客户实体 CRUD。

软删除：`delete()` 把 status 改成 `archived`，不真正删行（保留 license / api_key FK）。
"""
from __future__ import annotations

import secrets
from typing import Any, Sequence

from sqlalchemy import select

from app.adapters.database.interface.protocol import Database
from app.models.customer import CustomerModel


class CustomerSlugConflict(Exception):
    """同 slug 已存在。"""


class CustomerRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        *,
        slug: str,
        name: str,
        contact_email: str = "",
        contact_name: str = "",
        region: str = "",
        notes: str = "",
    ) -> CustomerModel:
        async with self._db.session() as sess:
            existing = await sess.execute(
                select(CustomerModel).where(CustomerModel.slug == slug)
            )
            if existing.scalar_one_or_none() is not None:
                raise CustomerSlugConflict(slug)
            model = CustomerModel(
                id=secrets.token_hex(12),
                slug=slug,
                name=name,
                contact_email=contact_email,
                contact_name=contact_name,
                region=region,
                notes=notes,
                status="active",
            )
            sess.add(model)
        return model

    async def get(self, customer_id: str) -> CustomerModel | None:
        async with self._db.session() as sess:
            return await sess.get(CustomerModel, customer_id)

    async def get_by_slug(self, slug: str) -> CustomerModel | None:
        async with self._db.session() as sess:
            stmt = select(CustomerModel).where(CustomerModel.slug == slug)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def list(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CustomerModel]:
        async with self._db.session() as sess:
            stmt = select(CustomerModel)
            if status is not None:
                stmt = stmt.where(CustomerModel.status == status)
            stmt = stmt.order_by(CustomerModel.created_at.desc()).limit(limit).offset(offset)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def update(
        self,
        customer_id: str,
        *,
        fields: dict[str, Any],
    ) -> CustomerModel | None:
        """直接更新指定字段；slug 不可修改（外键引用）。"""
        async with self._db.session() as sess:
            model = await sess.get(CustomerModel, customer_id)
            if model is None:
                return None
            for k, v in fields.items():
                if k == "slug" or k == "id":
                    continue  # 不允许改
                if hasattr(model, k):
                    setattr(model, k, v)
            await sess.flush()
            await sess.refresh(model)  # 拿到 server-side onupdate=now() 后的最新值
        return model

    async def archive(self, customer_id: str) -> CustomerModel | None:
        """软删除 —— status → archived。"""
        async with self._db.session() as sess:
            model = await sess.get(CustomerModel, customer_id)
            if model is None:
                return None
            model.status = "archived"
            await sess.flush()
            await sess.refresh(model)
        return model

    async def hard_delete(self, customer_id: str) -> dict[str, Any] | None:
        """硬删除 —— 真删行 + 级联删除该客户的 license / api_key / heartbeat / nonce / revocation。

        返回受影响行数明细（用于审计），不存在则 None。
        """
        from sqlalchemy import delete

        # Lazy import — 这些 model 跨 repo 也别强制 module-import 提前
        from app.models.api_key import ApiKeyModel
        from app.models.heartbeat import HeartbeatLogModel, HeartbeatNonceModel
        from app.models.license import LicenseModel
        from app.models.revocation import RevocationEntryModel

        async with self._db.session() as sess:
            model = await sess.get(CustomerModel, customer_id)
            if model is None:
                return None
            # 1) 先把该客户所有 license_id 拿出来 —— 级联到心跳/吊销/重放表
            license_ids = (
                await sess.execute(
                    select(LicenseModel.license_id).where(LicenseModel.customer_id == customer_id)
                )
            ).scalars().all()
            cascaded: dict[str, int] = {"customer": 0, "license": 0, "api_key": 0,
                                       "heartbeat_log": 0, "heartbeat_nonce": 0, "revocation": 0}
            if license_ids:
                cascaded["heartbeat_log"] = (await sess.execute(
                    delete(HeartbeatLogModel).where(HeartbeatLogModel.license_id.in_(license_ids))
                )).rowcount or 0
                cascaded["heartbeat_nonce"] = (await sess.execute(
                    delete(HeartbeatNonceModel).where(HeartbeatNonceModel.license_id.in_(license_ids))
                )).rowcount or 0
                cascaded["revocation"] = (await sess.execute(
                    delete(RevocationEntryModel).where(RevocationEntryModel.license_id.in_(license_ids))
                )).rowcount or 0
                cascaded["license"] = (await sess.execute(
                    delete(LicenseModel).where(LicenseModel.license_id.in_(license_ids))
                )).rowcount or 0
            cascaded["api_key"] = (await sess.execute(
                delete(ApiKeyModel).where(ApiKeyModel.customer_id == customer_id)
            )).rowcount or 0
            await sess.delete(model)
            cascaded["customer"] = 1
        return {"slug": model.slug, "cascaded": cascaded}
