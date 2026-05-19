"""密钥生命周期端到端：generate → save → encrypted on disk → load → sign → verify。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.key_storage.encryption import DecryptionFailed, decrypt, encrypt
from app.core.key_storage.interface import KeyStorageError
from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import (
    generate_and_save_signing_key,
    revoke_signing_key,
    rotate_signing_key,
)
from app.core.signing import get_signer


# ────────────────────────────────────────────────────────────
# encryption.py 单元测试
# ────────────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = b"\x01\x02\x03" * 32
    blob = encrypt(plaintext, "correct horse battery staple")
    assert decrypt(blob, "correct horse battery staple") == plaintext


def test_decrypt_wrong_passphrase() -> None:
    blob = encrypt(b"secret", "right-password")
    with pytest.raises(DecryptionFailed):
        decrypt(blob, "wrong-password")


def test_decrypt_tampered_ciphertext() -> None:
    blob = bytearray(encrypt(b"secret", "pw"))
    blob[-1] ^= 0x01  # 翻转最后一位（tag 区）
    with pytest.raises(DecryptionFailed):
        decrypt(bytes(blob), "pw")


def test_decrypt_bad_magic() -> None:
    blob = encrypt(b"secret", "pw")
    with pytest.raises(DecryptionFailed):
        decrypt(b"XXXX" + blob[4:], "pw")


def test_encrypt_each_call_produces_different_ciphertext() -> None:
    """同一明文 + 同一密码两次加密产生不同密文（salt + nonce 随机）。"""
    a = encrypt(b"hello", "pw")
    b = encrypt(b"hello", "pw")
    assert a != b


# ────────────────────────────────────────────────────────────
# local_file backend
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_load_roundtrip(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="test-master-passphrase")
    saved = await generate_and_save_signing_key(storage, algorithm="ed25519")

    loaded = await storage.load(saved.key_id)
    assert loaded.key_id == saved.key_id
    assert loaded.algorithm == "ed25519"
    assert loaded.public_key == saved.public_key
    assert loaded.private_key == saved.private_key
    assert loaded.status == "active"


@pytest.mark.asyncio
async def test_private_key_is_encrypted_on_disk(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw1")
    saved = await generate_and_save_signing_key(storage, algorithm="ed25519")

    on_disk = (tmp_path / saved.key_id / "private.enc").read_bytes()
    # 落盘内容不可能等于明文私钥
    assert on_disk != saved.private_key
    # 也不应该包含明文私钥
    assert saved.private_key not in on_disk
    # FRGK magic 头
    assert on_disk[:4] == b"FRGK"


@pytest.mark.asyncio
async def test_load_with_wrong_passphrase_fails(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="correct-pw")
    saved = await generate_and_save_signing_key(storage, algorithm="ed25519")

    wrong_storage = LocalFileKeyStorage(root=tmp_path, passphrase="wrong-pw")
    with pytest.raises(KeyStorageError):
        await wrong_storage.load(saved.key_id)


@pytest.mark.asyncio
async def test_load_nonexistent_key(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    with pytest.raises(KeyStorageError):
        await storage.load("does-not-exist")


@pytest.mark.asyncio
async def test_save_then_sign_then_verify(tmp_path: Path) -> None:
    """完整闭环：save → load → 用加载的私钥签 → 用加载的公钥验签。"""
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    record = await generate_and_save_signing_key(storage, algorithm="ed25519")

    # 模拟服务重启：完全重新构造 storage 读
    fresh_storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    loaded = await fresh_storage.load(record.key_id)

    signer = get_signer("ed25519")
    payload = b"hello, license"
    sig = signer.sign(private_key=loaded.private_key, key_id=loaded.key_id, payload=payload)
    assert signer.verify(public_key=loaded.public_key, payload=payload, signature=sig.signature)


@pytest.mark.asyncio
async def test_list_ids_and_load_public(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    r1 = await generate_and_save_signing_key(storage, algorithm="ed25519")
    r2 = await generate_and_save_signing_key(storage, algorithm="ed25519")

    ids = await storage.list_ids()
    assert sorted(ids) == sorted([r1.key_id, r2.key_id])

    public_key, algorithm = await storage.load_public(r1.key_id)
    assert public_key == r1.public_key
    assert algorithm == "ed25519"


@pytest.mark.asyncio
async def test_rotation_flow(tmp_path: Path) -> None:
    """轮换：旧密钥 status 变 rotated；新密钥 status=active；两把密钥都能验签各自时期的 license。"""
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    old = await generate_and_save_signing_key(storage, algorithm="ed25519")
    new = await rotate_signing_key(storage, algorithm="ed25519", previous_key_id=old.key_id)

    old_loaded = await storage.load(old.key_id)
    new_loaded = await storage.load(new.key_id)
    assert old_loaded.status == "rotated"
    assert new_loaded.status == "active"
    assert old.key_id != new.key_id

    # 旧密钥仍能签 + 验（用于已签发 license 的兼容）
    signer = get_signer("ed25519")
    sig = signer.sign(private_key=old_loaded.private_key, key_id=old_loaded.key_id, payload=b"x")
    assert signer.verify(public_key=old_loaded.public_key, payload=b"x", signature=sig.signature)


@pytest.mark.asyncio
async def test_revocation(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    rec = await generate_and_save_signing_key(storage, algorithm="ed25519")
    await revoke_signing_key(storage, rec.key_id)
    reloaded = await storage.load(rec.key_id)
    assert reloaded.status == "revoked"


@pytest.mark.asyncio
async def test_invalid_key_id_rejected(tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    with pytest.raises(KeyStorageError):
        await storage.load("../etc/passwd")
    with pytest.raises(KeyStorageError):
        await storage.load("path/with/slash")
