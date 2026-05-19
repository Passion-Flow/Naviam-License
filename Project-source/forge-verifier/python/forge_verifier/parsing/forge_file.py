"""`.forge` 容器解析（与 forge-server format.py 对偶；不共享代码）。"""
from __future__ import annotations

import io
import json
import tarfile
from dataclasses import dataclass
from datetime import datetime

from forge_verifier.parsing.payload import LicensePayload

FORGE_VERSION = "1.0"
FORGE_MAGIC = "forg"


class ForgeFileError(Exception):
    """`.forge` 解析失败。"""


@dataclass(frozen=True, slots=True)
class ForgeMetadata:
    magic: str
    forge_version: str
    algorithm: str
    key_id: str
    signed_at: datetime

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "ForgeMetadata":
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ForgeFileError(f"metadata.json malformed: {exc}") from exc
        if obj.get("magic") != FORGE_MAGIC:
            raise ForgeFileError(f"unexpected magic: {obj.get('magic')!r}")
        try:
            return cls(
                magic=obj["magic"],
                forge_version=obj["forge_version"],
                algorithm=obj["algorithm"],
                key_id=obj["key_id"],
                signed_at=datetime.fromisoformat(obj["signed_at"]),
            )
        except KeyError as exc:
            raise ForgeFileError(f"metadata missing field: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ForgeFile:
    payload: LicensePayload
    payload_canonical_bytes: bytes   # 保留原始字节流，用于验签（不可重新生成）
    signature: bytes
    metadata: ForgeMetadata


def unpack(data: bytes) -> ForgeFile:
    """解包 .forge tar，**保留 payload.json 原始字节**用于验签。

    注意：不能用解析后的对象重新序列化做验签——任何 JSON 库的微小差异都可能让签名不再匹配。
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
            files: dict[str, bytes] = {}
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                if member.name not in {"payload.json", "signature.bin", "metadata.json"}:
                    raise ForgeFileError(f"unexpected entry: {member.name!r}")
                extracted = tar.extractfile(member)
                if extracted is None:
                    raise ForgeFileError(f"unable to extract {member.name!r}")
                files[member.name] = extracted.read()
    except tarfile.TarError as exc:
        raise ForgeFileError(f"not a valid forge tarball: {exc}") from exc

    missing = {"payload.json", "signature.bin", "metadata.json"} - files.keys()
    if missing:
        raise ForgeFileError(f"missing entries: {sorted(missing)}")

    payload_bytes = files["payload.json"]
    return ForgeFile(
        payload=LicensePayload.from_canonical_bytes(payload_bytes),
        payload_canonical_bytes=payload_bytes,
        signature=files["signature.bin"],
        metadata=ForgeMetadata.from_json_bytes(files["metadata.json"]),
    )
