"""UserRepository —— 厂商 Admin 用户的存取。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update

from app.adapters.database.interface.protocol import Database
from app.core.auth.passwords import hash_password
from app.models.user import UserModel


class UserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        *,
        username: str,
        email: str,
        plaintext_password: str,
        is_super: bool = False,
    ) -> UserModel:
        user = UserModel(
            id=secrets.token_hex(12),
            username=username,
            email=email,
            password_hash=hash_password(plaintext_password),
            is_super=is_super,
            is_active=True,
        )
        async with self._db.session() as sess:
            sess.add(user)
        return user

    async def get_by_username(self, username: str) -> UserModel | None:
        async with self._db.session() as sess:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        async with self._db.session() as sess:
            stmt = select(UserModel).where(UserModel.email == email)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def get(self, user_id: str) -> UserModel | None:
        async with self._db.session() as sess:
            return await sess.get(UserModel, user_id)

    async def mark_login(self, user_id: str) -> None:
        async with self._db.session() as sess:
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(last_login_at=datetime.now(timezone.utc))
            )
            await sess.execute(stmt)

    async def update_password(self, user_id: str, *, new_plaintext: str) -> None:
        async with self._db.session() as sess:
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(password_hash=hash_password(new_plaintext))
            )
            await sess.execute(stmt)

    async def deactivate(self, user_id: str) -> None:
        async with self._db.session() as sess:
            stmt = update(UserModel).where(UserModel.id == user_id).values(is_active=False)
            await sess.execute(stmt)

    async def reactivate(self, user_id: str) -> None:
        async with self._db.session() as sess:
            stmt = update(UserModel).where(UserModel.id == user_id).values(is_active=True)
            await sess.execute(stmt)

    async def list_all(self) -> Sequence[UserModel]:
        async with self._db.session() as sess:
            stmt = select(UserModel).order_by(UserModel.username)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def hard_delete(self, user_id: str) -> bool:
        """硬删除管理员账号。审计日志（actor_id 引用）保留不动 —— append-only。"""
        from sqlalchemy import delete

        async with self._db.session() as sess:
            model = await sess.get(UserModel, user_id)
            if model is None:
                return False
            await sess.execute(delete(UserModel).where(UserModel.id == user_id))
        return True
