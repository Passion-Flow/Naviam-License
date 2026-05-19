"""`.forge` 文件容器格式。

`.forge` 是 tar 包，固定布局：
- payload.json    业务字段（LicensePayload.canonical_bytes() 的内容）
- signature.bin   detached signature（字节流）
- metadata.json   签名元信息：algorithm / key_id / signed_at / forge_version

`.forge` 是人可读（tar -tvf 可看），便于客户人工排障。
"""
from __future__ import annotations

import io
import json
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.license.payload import LicensePayload

# 容器格式版本——与 LicensePayload.protocol_version 分开演进
FORGE_VERSION = "1.0"
# tar 内部前 4 字节是 "forg" 用作快速识别（写在 metadata.json 的 magic 字段）
FORGE_MAGIC = "forg"


class ForgeFileError(Exception):
    """`.forge` 文件解析失败。"""


@dataclass(frozen=True, slots=True)
class ForgeMetadata:
    """`.forge` 文件中 metadata.json 的内容。"""

    algorithm: str          # ed25519 / rsa2048 / rsa4096 / sm2
    key_id: str             # 用于签名的密钥 ID
    signed_at: datetime     # 签发服务侧的签名时间（UTC）
    forge_version: str = FORGE_VERSION
    magic: str = FORGE_MAGIC

    def to_json_bytes(self) -> bytes:
        return json.dumps(
            {
                "magic": self.magic,
                "forge_version": self.forge_version,
                "algorithm": self.algorithm,
                "key_id": self.key_id,
                "signed_at": self.signed_at.astimezone(timezone.utc).isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

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
    """已组装的 .forge 文件三元组。"""

    payload: LicensePayload
    signature: bytes
    metadata: ForgeMetadata


def _add_tar_entry(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 0  # 固定 mtime 让相同输入产生 bit-identical 输出
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def pack(payload: LicensePayload, signature: bytes, metadata: ForgeMetadata) -> bytes:
    """组 .forge tar 包。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_tar_entry(tar, "payload.json", payload.canonical_bytes())
        _add_tar_entry(tar, "signature.bin", signature)
        _add_tar_entry(tar, "metadata.json", metadata.to_json_bytes())
    return buf.getvalue()


def unpack(data: bytes) -> ForgeFile:
    """解 .forge tar 包。"""
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

    metadata = ForgeMetadata.from_json_bytes(files["metadata.json"])
    payload = LicensePayload.from_canonical_bytes(files["payload.json"])
    signature = files["signature.bin"]
    return ForgeFile(payload=payload, signature=signature, metadata=metadata)
