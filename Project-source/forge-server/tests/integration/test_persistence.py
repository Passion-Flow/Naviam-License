"""真持久化端到端：SQLAlchemy 2 async + aiosqlite + 4 个 Repository。

注意：SQLite 在本项目中**仅作测试 backend**，不在 Service Database 4 providers 中（不是 provider）。
它的作用是：验证 ORM 模型 + Repository SQL 正确性，不引入 postgres 容器依赖。
真生产由 PostgresDatabase / MysqlDatabase / OracleDatabase / TidbDatabase 走真实 driver。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.database.postgres.adapter import PostgresDatabase
from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import CrlManager
from app.core.license.issuer import IssueLicenseRequest, issue_license_with_storage
from app.models import Base
from app.repositories import (
    ApiKeyRepository,
    DbBackedApiKeyAuth,
    DbBackedRevocationStore,
    LicenseRepository,
)


@pytest.fixture
async def db(tmp_path: Path):
    """SQLite 内存 DB —— 测试快、隔离好。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield PostgresDatabase.from_engine(engine)
    await engine.dispose()


# ────────────────────────────────────────────────────────────
# LicenseRepository
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_persist_issued_license_roundtrip(db, tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path / "keys", passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")

    req = IssueLicenseRequest(
        customer_id="c1",
        product_id="p1",
        mode="hybrid",
        scope="customer_x_product",
        algorithm="ed25519",
        binding="soft",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={"sso": True},
        limits={"max_users": 5},
    )
    issued = await issue_license_with_storage(storage=storage, req=req)

    repo = LicenseRepository(db)
    await repo.add_issued(issued)

    # 取回
    fetched = await repo.get(issued.license_id)
    assert fetched is not None
    assert fetched.customer_id == "c1"
    assert fetched.product_id == "p1"
    assert fetched.algorithm == "ed25519"
    assert fetched.binding == "soft"
    assert fetched.features == {"sso": True}
    assert fetched.limits == {"max_users": 5}
    assert fetched.payload_hash and len(fetched.payload_hash) == 64
    assert fetched.forge_file == issued.forge_file


@pytest.mark.asyncio
async def test_list_for_customer(db, tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path / "keys", passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")
    repo = LicenseRepository(db)

    base_req = dict(
        product_id="p", mode="offline", scope="instance",
        algorithm="ed25519", binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={}, limits={},
    )
    # cust-A: 2 张；cust-B: 1 张
    for cust in ["cust-A", "cust-A", "cust-B"]:
        issued = await issue_license_with_storage(
            storage=storage,
            req=IssueLicenseRequest(customer_id=cust, **base_req),
        )
        await repo.add_issued(issued)

    a_licenses = await repo.list_for_customer("cust-A")
    b_licenses = await repo.list_for_customer("cust-B")
    assert len(a_licenses) == 2
    assert len(b_licenses) == 1


# ────────────────────────────────────────────────────────────
# ApiKeyRepository + DbBackedApiKeyAuth
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_key_issue_and_lookup(db) -> None:
    repo = ApiKeyRepository(db)
    model, plaintext = await repo.issue(customer_id="cust-1", project_label="proj-x")
    assert model.status == "active"
    assert model.key_prefix == plaintext[:8]
    assert len(plaintext) > 30  # 强熵

    auth = DbBackedApiKeyAuth(repo)
    info = await auth.lookup(plaintext)
    assert info is not None
    assert info.customer_id == "cust-1"

    # 错明文 → None
    assert await auth.lookup("wrong-key") is None


@pytest.mark.asyncio
async def test_api_key_revocation_blocks_lookup(db) -> None:
    repo = ApiKeyRepository(db)
    model, plaintext = await repo.issue(customer_id="c", project_label="p")
    await repo.revoke(model.key_id)

    auth = DbBackedApiKeyAuth(repo)
    info = await auth.lookup(plaintext)
    assert info is None  # revoked 不应通过


@pytest.mark.asyncio
async def test_api_key_mark_used_updates_last_used_at(db) -> None:
    repo = ApiKeyRepository(db)
    model, plaintext = await repo.issue(customer_id="c", project_label="p")
    assert model.last_used_at is None

    await repo.mark_used(model.key_id)
    # 重新查
    refetched = await repo.find_by_plaintext(plaintext)
    assert refetched is not None
    assert refetched.last_used_at is not None


# ────────────────────────────────────────────────────────────
# DbBackedRevocationStore + CrlManager
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_db_backed_revocation_store(db, tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path / "keys", passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")

    store = DbBackedRevocationStore(db)
    manager = CrlManager(store=store, key_storage=storage, algorithm="ed25519")

    await manager.revoke("lic-abc", reason="leaked")
    await manager.revoke("lic-xyz", reason="terminated")

    crl_bytes = await manager.generate_crl()
    assert len(crl_bytes) > 100

    from app.core.license.crl import unpack_crl
    crl = unpack_crl(crl_bytes)
    assert {e.license_id for e in crl.payload.entries} == {"lic-abc", "lic-xyz"}
    assert crl.payload.sequence >= 1


@pytest.mark.asyncio
async def test_revocation_unrevoke_removes_entry(db, tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path / "keys", passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")
    store = DbBackedRevocationStore(db)
    manager = CrlManager(store=store, key_storage=storage, algorithm="ed25519")
    await manager.revoke("lic-1")
    await manager.unrevoke("lic-1")

    from app.core.license.crl import unpack_crl
    crl = unpack_crl(await manager.generate_crl())
    assert crl.payload.entries == []


@pytest.mark.asyncio
async def test_revocation_persists_across_repos(db, tmp_path: Path) -> None:
    """同一 DB 上构造两个 store 实例，第二个能看到第一个写入的 entries。"""
    storage = LocalFileKeyStorage(root=tmp_path / "keys", passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")

    store_a = DbBackedRevocationStore(db)
    await store_a.add("lic-shared", reason="leaked")

    store_b = DbBackedRevocationStore(db)
    entries = await store_b.list_entries()
    assert {e.license_id for e in entries} == {"lic-shared"}
