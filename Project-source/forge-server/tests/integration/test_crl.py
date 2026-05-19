"""CRL 端到端（server 侧）：
revoke → generate CRL → unpack 验证 payload 内容 + 用 storage 公钥验签。
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import (
    CrlManager,
    InMemoryRevocationStore,
    unpack_crl,
)
from app.core.signing import get_signer


@pytest.mark.asyncio
async def test_generate_empty_crl(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    key = await generate_and_save_signing_key(storage, algorithm="ed25519")

    manager = CrlManager(store=InMemoryRevocationStore(), key_storage=storage, algorithm="ed25519")
    crl_bytes = await manager.generate_crl()

    crl = unpack_crl(crl_bytes)
    assert crl.payload.sequence == 1
    assert crl.payload.entries == []
    assert crl.metadata.algorithm == "ed25519"
    assert crl.metadata.key_id == key.key_id

    # 验签
    signer = get_signer("ed25519")
    assert signer.verify(
        public_key=key.public_key,
        payload=crl.payload_canonical_bytes,
        signature=crl.signature,
    )


@pytest.mark.asyncio
async def test_revoke_then_generate_includes_entry(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")
    manager = CrlManager(store=InMemoryRevocationStore(), key_storage=storage, algorithm="ed25519")

    await manager.revoke("lic-abc", reason="leaked")
    await manager.revoke("lic-xyz", reason="customer terminated")

    crl_bytes = await manager.generate_crl()
    crl = unpack_crl(crl_bytes)
    assert {e.license_id for e in crl.payload.entries} == {"lic-abc", "lic-xyz"}
    assert crl.payload.sequence == 1


@pytest.mark.asyncio
async def test_sequence_advances_on_content_change(tmp_path: Path) -> None:
    """sequence 在**内容变更**时单调递增；内容未变时复用上一次（CRL caching, Round AE）。

    [2026-05-14 起] 旧行为是"每次 generate 都 +1"，现在改成内容散列驱动 ——
    这样 ETag 跨进程稳定、verifier 端能 304、KMS 后端不被无谓签名调用淹没。
    """
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")
    manager = CrlManager(store=InMemoryRevocationStore(), key_storage=storage, algorithm="ed25519")

    # 第一次构造：sequence=1
    crl1 = unpack_crl(await manager.generate_crl())
    # 内容未变：sequence 不变
    crl2 = unpack_crl(await manager.generate_crl())
    assert crl1.payload.sequence == crl2.payload.sequence

    # 新增吊销项 → 内容变 → sequence 必须前进
    await manager.revoke("lic-1", reason="x")
    crl3 = unpack_crl(await manager.generate_crl())
    assert crl3.payload.sequence > crl1.payload.sequence

    # 再次同内容 → 继续复用
    crl4 = unpack_crl(await manager.generate_crl())
    assert crl4.payload.sequence == crl3.payload.sequence


@pytest.mark.asyncio
async def test_unrevoke_removes_entry(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    await generate_and_save_signing_key(storage, algorithm="ed25519")
    manager = CrlManager(store=InMemoryRevocationStore(), key_storage=storage, algorithm="ed25519")

    await manager.revoke("lic-1", reason="oops")
    await manager.unrevoke("lic-1")
    crl = unpack_crl(await manager.generate_crl())
    assert crl.payload.entries == []


@pytest.mark.asyncio
async def test_tampered_crl_payload_fails_verify(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    key = await generate_and_save_signing_key(storage, algorithm="ed25519")
    manager = CrlManager(store=InMemoryRevocationStore(), key_storage=storage, algorithm="ed25519")
    await manager.revoke("lic-1")
    crl_bytes = await manager.generate_crl()

    tampered = crl_bytes.replace(b"lic-1", b"lic-2")
    assert tampered != crl_bytes
    crl = unpack_crl(tampered)
    signer = get_signer("ed25519")
    assert not signer.verify(
        public_key=key.public_key,
        payload=crl.payload_canonical_bytes,
        signature=crl.signature,
    )
