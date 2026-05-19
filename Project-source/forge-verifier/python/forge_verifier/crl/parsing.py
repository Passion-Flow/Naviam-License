"""CRL 解析 —— Verifier 侧独立实现，与 forge-server format.py 对偶。"""
from __future__ import annotations

import io
import json
import tarfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

CRL_MAGIC = "crl"


class CrlFileError(Exception):
    """CRL 解析失败。"""


@dataclass(frozen=True, slots=True)
class RevocationEntry:
    license_id: str
    revoked_at: datetime
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RevocationListPayload:
    crl_version: str
    sequence: int
    issued_at: datetime
    next_update_at: datetime
    entries: list[RevocationEntry]

    @classmethod
    def from_canonical_bytes(cls, raw: bytes) -> "RevocationListPayload":
        obj = json.loads(raw.decode("utf-8"))
        return cls(
            crl_version=obj["crl_version"],
            sequence=int(obj["sequence"]),
            issued_at=datetime.fromisoformat(obj["issued_at"]),
            next_update_at=datetime.fromisoformat(obj["next_update_at"]),
            entries=[
                RevocationEntry(
                    license_id=e["license_id"],
                    revoked_at=datetime.fromisoformat(e["revoked_at"]),
                    reason=e.get("reason", ""),
                )
                for e in obj.get("entries", [])
            ],
        )

    def contains(self, license_id: str) -> RevocationEntry | None:
        for e in self.entries:
            if e.license_id == license_id:
                return e
        return None


@dataclass(frozen=True, slots=True)
class CrlMetadata:
    magic: str
    crl_format_version: str
    algorithm: str
    key_id: str
    signed_at: datetime

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "CrlMetadata":
        try:
            obj: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CrlFileError(f"crl metadata malformed: {exc}") from exc
        if obj.get("magic") != CRL_MAGIC:
            raise CrlFileError(f"unexpected magic: {obj.get('magic')!r}")
        try:
            return cls(
                magic=obj["magic"],
                crl_format_version=obj["crl_format_version"],
                algorithm=obj["algorithm"],
                key_id=obj["key_id"],
                signed_at=datetime.fromisoformat(obj["signed_at"]),
            )
        except KeyError as exc:
            raise CrlFileError(f"crl metadata missing field: {exc}") from exc


@dataclass(frozen=True, slots=True)
class CrlFile:
    payload: RevocationListPayload
    payload_canonical_bytes: bytes
    signature: bytes
    metadata: CrlMetadata


def unpack_crl(data: bytes) -> CrlFile:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
            files: dict[str, bytes] = {}
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                if member.name not in {"payload.json", "signature.bin", "metadata.json"}:
                    raise CrlFileError(f"unexpected entry: {member.name!r}")
                extracted = tar.extractfile(member)
                if extracted is None:
                    raise CrlFileError(f"unable to extract {member.name!r}")
                files[member.name] = extracted.read()
    except tarfile.TarError as exc:
        raise CrlFileError(f"not a valid crl tarball: {exc}") from exc

    missing = {"payload.json", "signature.bin", "metadata.json"} - files.keys()
    if missing:
        raise CrlFileError(f"missing entries: {sorted(missing)}")

    payload_bytes = files["payload.json"]
    return CrlFile(
        payload=RevocationListPayload.from_canonical_bytes(payload_bytes),
        payload_canonical_bytes=payload_bytes,
        signature=files["signature.bin"],
        metadata=CrlMetadata.from_json_bytes(files["metadata.json"]),
    )
