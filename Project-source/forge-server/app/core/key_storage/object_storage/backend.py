"""object_storage backend —— 同 local_file 加密格式，落点改为 object storage bucket。

key 在 bucket 中的布局：
    <bucket>/
    └── keys/
        └── <key_id>/
            ├── public.bin
            ├── private.enc        ← 与 local_file 同样的 FRGK AES-GCM 格式
            └── metadata.json
"""
from __future__ import annotations

import json
from datetime import datetime

from app.adapters.object_storage import ObjectStorage, get_object_storage
from app.core.key_storage.encryption import DecryptionFailed, decrypt, encrypt
from app.core.key_storage.interface import KeyRecord, KeyStatus, KeyStorage, KeyStorageError
from app.settings import Settings


class ObjectStorageKeyStorage(KeyStorage):
    backend_name = "object_storage"

    def __init__(
        self,
        *,
        storage: ObjectStorage,
        bucket: str,
        passphrase: str,
        prefix: str = "keys",
    ) -> None:
        if not passphrase:
            raise ValueError("object_storage backend requires a non-empty passphrase")
        if not bucket:
            raise ValueError("object_storage backend requires a bucket name")
        self._storage = storage
        self._bucket = bucket
        self._passphrase = passphrase
        self._prefix = prefix.strip("/")

    @classmethod
    def from_settings(cls, settings: Settings) -> "ObjectStorageKeyStorage":
        return cls(
            storage=get_object_storage(),
            bucket=settings.object_storage_bucket_public_keys,  # 复用同一 bucket，前缀区分
            passphrase=settings.key_master_passphrase,
        )

    def _key(self, key_id: str, suffix: str) -> str:
        if not key_id or "/" in key_id or ".." in key_id:
            raise KeyStorageError(f"invalid key_id: {key_id!r}")
        return f"{self._prefix}/{key_id}/{suffix}"

    async def save(self, record: KeyRecord) -> None:
        await self._storage.put(
            self._bucket,
            self._key(record.key_id, "public.bin"),
            record.public_key,
            content_type="application/octet-stream",
        )
        await self._storage.put(
            self._bucket,
            self._key(record.key_id, "private.enc"),
            encrypt(record.private_key, self._passphrase),
            content_type="application/octet-stream",
        )
        meta = {
            "key_id": record.key_id,
            "algorithm": record.algorithm,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "activated_at": record.activated_at.isoformat() if record.activated_at else None,
            "rotated_at": record.rotated_at.isoformat() if record.rotated_at else None,
            "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        }
        await self._storage.put(
            self._bucket,
            self._key(record.key_id, "metadata.json"),
            json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            content_type="application/json",
        )

    async def load(self, key_id: str) -> KeyRecord:
        try:
            public_key = await self._storage.get(self._bucket, self._key(key_id, "public.bin"))
            encrypted = await self._storage.get(self._bucket, self._key(key_id, "private.enc"))
            meta_bytes = await self._storage.get(self._bucket, self._key(key_id, "metadata.json"))
        except Exception as exc:
            raise KeyStorageError(f"failed to read key {key_id}") from exc

        try:
            private_key = decrypt(encrypted, self._passphrase)
        except DecryptionFailed as exc:
            raise KeyStorageError(f"private key decrypt failed for {key_id}") from exc

        meta = json.loads(meta_bytes.decode("utf-8"))
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

    async def list_ids(self) -> list[str]:
        ids = set()
        async for meta in self._storage.list_(self._bucket, prefix=f"{self._prefix}/"):
            # 形如 keys/<key_id>/metadata.json
            parts = meta.key.split("/")
            if len(parts) >= 3 and parts[-1] == "metadata.json":
                ids.add(parts[-2])
        return sorted(ids)

    async def load_public(self, key_id: str) -> tuple[bytes, str]:
        try:
            public_key = await self._storage.get(self._bucket, self._key(key_id, "public.bin"))
            meta_bytes = await self._storage.get(self._bucket, self._key(key_id, "metadata.json"))
        except Exception as exc:
            raise KeyStorageError(f"failed to read public key {key_id}") from exc
        meta = json.loads(meta_bytes.decode("utf-8"))
        return public_key, meta["algorithm"]

    async def update_status(self, key_id: str, status: KeyStatus) -> None:
        try:
            meta_bytes = await self._storage.get(self._bucket, self._key(key_id, "metadata.json"))
        except Exception as exc:
            raise KeyStorageError(f"key not found: {key_id}") from exc
        meta = json.loads(meta_bytes.decode("utf-8"))
        meta["status"] = status
        now = datetime.utcnow().isoformat()
        if status == "rotated":
            meta["rotated_at"] = now
        elif status == "revoked":
            meta["revoked_at"] = now
        elif status == "active" and not meta.get("activated_at"):
            meta["activated_at"] = now
        await self._storage.put(
            self._bucket,
            self._key(key_id, "metadata.json"),
            json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            content_type="application/json",
        )

    async def delete(self, key_id: str) -> None:
        for suffix in ("public.bin", "private.enc", "metadata.json"):
            try:
                await self._storage.delete(self._bucket, self._key(key_id, suffix))
            except Exception:
                pass  # best effort
