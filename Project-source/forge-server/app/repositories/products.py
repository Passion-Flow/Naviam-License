"""ProductRepository —— 产品定义 CRUD（无删除：只能 archive）。"""
from __future__ import annotations

import secrets
from typing import Any, Sequence

from sqlalchemy import select

from app.adapters.database.interface.protocol import Database
from app.models.product import ProductModel


class ProductSlugConflict(Exception):
    """同 slug 已存在。"""


class ProductRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        *,
        slug: str,
        name: str,
        description: str = "",
        version: str = "",
        features_schema: dict[str, Any] | None = None,
        default_limits: dict[str, Any] | None = None,
    ) -> ProductModel:
        async with self._db.session() as sess:
            existing = await sess.execute(
                select(ProductModel).where(ProductModel.slug == slug)
            )
            if existing.scalar_one_or_none() is not None:
                raise ProductSlugConflict(slug)
            model = ProductModel(
                id=secrets.token_hex(12),
                slug=slug,
                name=name,
                description=description,
                version=version,
                features_schema=features_schema or {},
                default_limits=default_limits or {},
                status="active",
            )
            sess.add(model)
        return model

    async def get(self, product_id: str) -> ProductModel | None:
        async with self._db.session() as sess:
            return await sess.get(ProductModel, product_id)

    async def get_by_slug(self, slug: str) -> ProductModel | None:
        async with self._db.session() as sess:
            stmt = select(ProductModel).where(ProductModel.slug == slug)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def list(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ProductModel]:
        async with self._db.session() as sess:
            stmt = select(ProductModel)
            if status is not None:
                stmt = stmt.where(ProductModel.status == status)
            stmt = stmt.order_by(ProductModel.created_at.desc()).limit(limit).offset(offset)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def update(
        self,
        product_id: str,
        *,
        fields: dict[str, Any],
    ) -> ProductModel | None:
        async with self._db.session() as sess:
            model = await sess.get(ProductModel, product_id)
            if model is None:
                return None
            for k, v in fields.items():
                if k in ("slug", "id"):
                    continue
                if hasattr(model, k):
                    setattr(model, k, v)
            await sess.flush()
            await sess.refresh(model)
        return model

    async def hard_delete(self, product_id: str) -> dict[str, Any] | None:
        """硬删除 —— 真删行 + 级联删除该产品的 license / heartbeat / nonce / revocation。"""
        from sqlalchemy import delete

        from app.models.heartbeat import HeartbeatLogModel, HeartbeatNonceModel
        from app.models.license import LicenseModel
        from app.models.revocation import RevocationEntryModel

        async with self._db.session() as sess:
            model = await sess.get(ProductModel, product_id)
            if model is None:
                return None
            license_ids = (
                await sess.execute(
                    select(LicenseModel.license_id).where(LicenseModel.product_id == product_id)
                )
            ).scalars().all()
            cascaded: dict[str, int] = {"product": 0, "license": 0,
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
            await sess.delete(model)
            cascaded["product"] = 1
        return {"slug": model.slug, "cascaded": cascaded}
