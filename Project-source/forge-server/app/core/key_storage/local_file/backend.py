"""local_file backend —— 私钥加密存本地路径。

每个 key 一个目录：
    <KEY_STORAGE_LOCAL_PATH>/
    └── <key_id>/
        ├── public.bin       公钥（明文）
        ├── private.enc      私钥密文（FRGK 格式）
        └── metadata.json    算法 / 状态 / 时间戳（明文，不含敏感）

注意：
- 整个目录建议 chmod 0700；private.enc chmod 0600
- 主口令（passphrase）从 settings.key_master_passphrase 取，**绝不**写入任何元数据
- 这是私有化交付的默认 backend；高安全场景客户应换 KMS
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.core.key_storage.encryption import DecryptionFailed, decrypt, encrypt
from app.core.key_storage.interface import KeyRecord, KeyStatus, KeyStorage, KeyStorageError
from app.settings import Settings


class LocalFileKeyStorage(KeyStorage):
    backend_name = "local_file"

    def __init__(self, root: Path, passphrase: str) -> None:
        if not passphrase:
            raise ValueError("local_file backend requires a non-empty passphrase")
        self._root = root
        self._passphrase = passphrase

    @classmethod
    def from_settings(cls, settings: Settings) -> "LocalFileKeyStorage":
        return cls(
            root=Path(settings.key_storage_local_path),
            passphrase=settings.key_master_passphrase,
        )

    # ── 异步 wrap：本地 IO 走 asyncio.to_thread，不阻塞事件循环 ──
    async def save(self, record: KeyRecord) -> None:
        await asyncio.to_thread(self._save_sync, record)

    async def load(self, key_id: str) -> KeyRecord:
        return await asyncio.to_thread(self._load_sync, key_id)

    async def list_ids(self) -> list[str]:
        return await asyncio.to_thread(self._list_ids_sync)

    async def load_public(self, key_id: str) -> tuple[bytes, str]:
        return await asyncio.to_thread(self._load_public_sync, key_id)

    async def update_status(self, key_id: str, status: KeyStatus) -> None:
        await asyncio.to_thread(self._update_status_sync, key_id, status)

    async def delete(self, key_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, key_id)

    # ── 同步实现 ──
    def _key_dir(self, key_id: str) -> Path:
        if not key_id or "/" in key_id or ".." in key_id:
            raise KeyStorageError(f"invalid key_id: {key_id!r}")
        return self._root / key_id

    def _save_sync(self, record: KeyRecord) -> None:
        key_dir = self._key_dir(record.key_id)
        key_dir.mkdir(parents=True, exist_ok=True)
        try:
            key_dir.chmod(0o700)
        except OSError:
            pass

        encrypted = encrypt(record.private_key, self._passphrase)

        # 原子写：tmp + replace
        (self._tmp(key_dir / "public.bin")).write_bytes(record.public_key)
        (key_dir / "public.bin.tmp").replace(key_dir / "public.bin")

        (self._tmp(key_dir / "private.enc")).write_bytes(encrypted)
        (key_dir / "private.enc.tmp").replace(key_dir / "private.enc")
        try:
            (key_dir / "private.enc").chmod(0o600)
        except OSError:
            pass

        meta = {
            "key_id": record.key_id,
            "algorithm": record.algorithm,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "activated_at": record.activated_at.isoformat() if record.activated_at else None,
            "rotated_at": record.rotated_at.isoformat() if record.rotated_at else None,
            "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        }
        (self._tmp(key_dir / "metadata.json")).write_text(
            json.dumps(meta, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        (key_dir / "metadata.json.tmp").replace(key_dir / "metadata.json")

    def _load_sync(self, key_id: str) -> KeyRecord:
        key_dir = self._key_dir(key_id)
        if not key_dir.exists():
            raise KeyStorageError(f"key not found: {key_id}")

        try:
            public_key = (key_dir / "public.bin").read_bytes()
            encrypted = (key_dir / "private.enc").read_bytes()
            meta = json.loads((key_dir / "metadata.json").read_text(encoding="utf-8"))
        except OSError as exc:
            raise KeyStorageError(f"failed to read key files: {exc}") from exc

        try:
            private_key = decrypt(encrypted, self._passphrase)
        except DecryptionFailed as exc:
            raise KeyStorageError(f"private key decrypt failed for {key_id}") from exc

        return KeyRecord(
            key_id=meta["key_id"],
            algorithm=meta["algorithm"],
            public_key=public_key,
            private_key=private_key,
            status=meta["status"],
            created_at=datetime.fromisoformat(meta["created_at"]),
            activated_at=datetime.fromisoformat(meta["activated_at"]) if meta.get("activated_at") else None,
            rotated_at=datetime.fromisoformat(meta["rotated_at"]) if meta.get("rotated_at") else None,
            revoked_at=datetime.fromisoformat(meta["revoked_at"]) if meta.get("revoked_at") else None,
        )

    def _list_ids_sync(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(p.name for p in self._root.iterdir() if p.is_dir() and (p / "metadata.json").exists())

    def _load_public_sync(self, key_id: str) -> tuple[bytes, str]:
        key_dir = self._key_dir(key_id)
        if not key_dir.exists():
            raise KeyStorageError(f"key not found: {key_id}")
        try:
            public_key = (key_dir / "public.bin").read_bytes()
            meta = json.loads((key_dir / "metadata.json").read_text(encoding="utf-8"))
        except OSError as exc:
            raise KeyStorageError(f"failed to read public key files: {exc}") from exc
        return public_key, meta["algorithm"]

    def _update_status_sync(self, key_id: str, status: KeyStatus) -> None:
        key_dir = self._key_dir(key_id)
        meta_path = key_dir / "metadata.json"
        if not meta_path.exists():
            raise KeyStorageError(f"key not found: {key_id}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = status
        now = datetime.utcnow().isoformat()
        if status == "rotated":
            meta["rotated_at"] = now
        elif status == "revoked":
            meta["revoked_at"] = now
        elif status == "active" and not meta.get("activated_at"):
            meta["activated_at"] = now
        tmp = self._tmp(meta_path)
        tmp.write_text(json.dumps(meta, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        tmp.replace(meta_path)

    def _delete_sync(self, key_id: str) -> None:
        key_dir = self._key_dir(key_id)
        if not key_dir.exists():
            return
        # 删除前先覆盖私钥文件（best effort，不能挡 forensic recovery）
        priv = key_dir / "private.enc"
        if priv.exists():
            try:
                priv.write_bytes(b"\x00" * priv.stat().st_size)
            except OSError:
                pass
        for child in key_dir.iterdir():
            child.unlink()
        key_dir.rmdir()

    @staticmethod
    def _tmp(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".tmp")
