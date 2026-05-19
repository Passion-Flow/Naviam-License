"""bootstrap_admin CLI 端到端：
- 首次调用 → created，is_super=True
- 第二次调用 → reused，不改密
- 显式覆盖 username / email / password → 落到新 user
- 主入口 `main(["--json"])` 输出 JSON
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.database.postgres.adapter import PostgresDatabase
from app.cli.bootstrap_admin import bootstrap_admin
from app.cli.bootstrap_admin.run import main
from app.core.auth.passwords import verify_password
from app.models import Base
from app.repositories.users import UserRepository
from app.settings import Settings


@pytest.fixture
def settings(tmp_path: Path):
    import os
    env = {
        "DATABASE_HOST": "localhost", "DATABASE_PORT": "5432",
        "DATABASE_USERNAME": "test", "DATABASE_PASSWORD": "test", "DATABASE_DATABASE": "test",
        "CACHE_HOST": "localhost", "CACHE_PORT": "6379", "CACHE_PASSWORD": "test",
        "KEY_STORAGE_BACKEND": "local_file",
        "KEY_STORAGE_LOCAL_PATH": str(tmp_path / "keys"),
        "KEY_MASTER_PASSPHRASE": "test-pass",
        "AUTH_SESSION_SECRET": "test-session-xxxxxxxx",
        "OBJECT_STORAGE_TYPE": "local",
        # 默认 bootstrap 字段 — 测试不显式传时走这些
        "BOOTSTRAP_ADMIN_USERNAME": "TestAdmin",
        "BOOTSTRAP_ADMIN_EMAIL": "test-admin@forge.local",
        "BOOTSTRAP_ADMIN_PASSWORD": "test-default-password",
    }
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    # 清缓存避免 get_settings() 拿到旧值
    from app.settings import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        yield Settings()  # type: ignore[call-arg]
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield PostgresDatabase.from_engine(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_creates_admin_on_first_run(settings, db) -> None:
    result = await bootstrap_admin(db=db)
    assert result.status == "created"
    assert result.username == "TestAdmin"

    repo = UserRepository(db)
    user = await repo.get_by_username("TestAdmin")
    assert user is not None
    assert user.is_super is True
    assert user.email == "test-admin@forge.local"
    assert verify_password("test-default-password", user.password_hash) is True


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent(settings, db) -> None:
    first = await bootstrap_admin(db=db)
    second = await bootstrap_admin(db=db)
    third = await bootstrap_admin(db=db)

    assert first.status == "created"
    assert second.status == "reused"
    assert third.status == "reused"
    # 同一个 user
    assert second.user_id == first.user_id
    assert third.user_id == first.user_id


@pytest.mark.asyncio
async def test_bootstrap_reused_does_not_change_password(settings, db) -> None:
    """已有 admin 时 reused —— 即使 password 参数与原值不同也不能改密。"""
    await bootstrap_admin(db=db)
    result = await bootstrap_admin(db=db, password="totally-different-password")
    assert result.status == "reused"

    repo = UserRepository(db)
    user = await repo.get_by_username("TestAdmin")
    assert user is not None
    # 原密码仍然有效；新密码不应被接受
    assert verify_password("test-default-password", user.password_hash) is True
    assert verify_password("totally-different-password", user.password_hash) is False


@pytest.mark.asyncio
async def test_bootstrap_explicit_override(settings, db) -> None:
    result = await bootstrap_admin(
        db=db,
        username="OverriddenAdmin",
        email="override@forge.local",
        password="custom-pw-123",
    )
    assert result.status == "created"
    assert result.username == "OverriddenAdmin"

    repo = UserRepository(db)
    user = await repo.get_by_username("OverriddenAdmin")
    assert user is not None
    assert user.email == "override@forge.local"
    assert verify_password("custom-pw-123", user.password_hash) is True
    # 默认 admin 用户不存在
    assert await repo.get_by_username("TestAdmin") is None


def test_main_argparse_smoke() -> None:
    """`main(["--help"])` 不应在 argparse 解析阶段崩溃；执行实际数据库逻辑由上面 4 个
    异步用例验证。这里只确认 CLI 入口的入参 / 出参面板没被破坏。"""
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
