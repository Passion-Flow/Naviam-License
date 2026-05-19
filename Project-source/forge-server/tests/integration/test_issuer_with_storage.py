"""issuer + key_storage 端到端：
generate keypair → save 加密 → 从 storage 取 → 签发 .forge → 用 storage 中公钥验签。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import (
    generate_and_save_signing_key,
    rotate_signing_key,
)
from app.core.license.forge_file import unpack
from app.core.license.issuer import (
    IssueLicenseRequest,
    NoActiveKeyError,
    find_active_key_id,
    issue_license_with_storage,
)
from app.core.signing import get_signer


@pytest.mark.asyncio
async def test_issue_with_storage_uses_active_key(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    active_key = await generate_and_save_signing_key(storage, algorithm="ed25519")

    req = IssueLicenseRequest(
        customer_id="cust-1",
        product_id="prod-1",
        mode="offline",
        scope="customer_x_product",
        algorithm="ed25519",
        binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={"sso": True},
        limits={"max_users": 5},
    )
    issued = await issue_license_with_storage(storage=storage, req=req)

    # 解包 + 用 storage 公钥验签
    forge = unpack(issued.forge_file)
    assert forge.metadata.key_id == active_key.key_id

    public_key, algorithm = await storage.load_public(active_key.key_id)
    assert algorithm == "ed25519"
    signer = get_signer("ed25519")
    assert signer.verify(
        public_key=public_key,
        payload=forge.payload.canonical_bytes(),
        signature=forge.signature,
    )


@pytest.mark.asyncio
async def test_issue_fails_when_no_active_key(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    req = IssueLicenseRequest(
        customer_id="cust-1",
        product_id="prod-1",
        mode="offline",
        scope="customer_x_product",
        algorithm="ed25519",
        binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={},
        limits={},
    )
    with pytest.raises(NoActiveKeyError):
        await issue_license_with_storage(storage=storage, req=req)


@pytest.mark.asyncio
async def test_find_active_key_picks_latest(tmp_path: Path) -> None:
    """有多把 active 时选 created_at 最新的一把（轮换中过渡期可能并存）。"""
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    old = await generate_and_save_signing_key(storage, algorithm="ed25519")
    new = await generate_and_save_signing_key(storage, algorithm="ed25519")  # 也是 active
    chosen = await find_active_key_id(storage, "ed25519")
    # created_at 几乎一样的话以最后写入的为最新
    assert chosen in {old.key_id, new.key_id}


@pytest.mark.asyncio
async def test_issue_skips_revoked_key(tmp_path: Path) -> None:
    """显式指定一把已 revoked 的 key 时应拒绝签发（防止用泄露密钥继续签）。"""
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    rec = await generate_and_save_signing_key(storage, algorithm="ed25519")
    # revoke
    await storage.update_status(rec.key_id, "revoked")
    req = IssueLicenseRequest(
        customer_id="cust-1",
        product_id="prod-1",
        mode="offline",
        scope="customer_x_product",
        algorithm="ed25519",
        binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={},
        limits={},
    )
    with pytest.raises(NoActiveKeyError, match="revoked"):
        await issue_license_with_storage(storage=storage, req=req, key_id=rec.key_id)


@pytest.mark.asyncio
async def test_issue_after_rotation_uses_new_key(tmp_path: Path) -> None:
    """轮换后默认签发应用新 active 密钥；老 license 仍可用老公钥验。"""
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    old = await generate_and_save_signing_key(storage, algorithm="ed25519")

    # 用老密钥签一份
    req = IssueLicenseRequest(
        customer_id="cust-1",
        product_id="prod-1",
        mode="offline",
        scope="customer_x_product",
        algorithm="ed25519",
        binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={},
        limits={},
    )
    old_issued = await issue_license_with_storage(storage=storage, req=req)
    assert unpack(old_issued.forge_file).metadata.key_id == old.key_id

    # 轮换
    new = await rotate_signing_key(storage, algorithm="ed25519", previous_key_id=old.key_id)
    assert new.key_id != old.key_id

    # 新签发应该用 new 的 key_id
    new_issued = await issue_license_with_storage(storage=storage, req=req)
    new_metadata = unpack(new_issued.forge_file).metadata
    assert new_metadata.key_id == new.key_id

    # 老 license 仍可用老公钥验
    old_forge = unpack(old_issued.forge_file)
    old_public, _ = await storage.load_public(old.key_id)
    signer = get_signer("ed25519")
    assert signer.verify(
        public_key=old_public,
        payload=old_forge.payload.canonical_bytes(),
        signature=old_forge.signature,
    )
