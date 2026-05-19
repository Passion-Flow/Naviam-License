"""CRL 文件格式 —— 与 .forge 结构对称：tar 包 + payload + signature + metadata。

文件扩展名约定：`.crl`（compose / helm 不绑文件名）

布局：
    payload.json    RevocationListPayload 规范化字节流
    signature.bin   LA 签名（同 license 签发的密钥）
    metadata.json   { magic="crl", crl_format_version, algorithm, key_id, signed_at }

序列化规范：与 LicensePayload **完全一致**（sort_keys + no-space + UTF-8）。
"""
from __future__ import annotations

import io
import json
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

CRL_FORMAT_VERSION = "1.0"
CRL_MAGIC = "crl"


class CrlFileError(Exception):
    """CRL 文件解析失败。"""


class RevocationEntry(BaseModel):
    """单条吊销记录。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    license_id: str = Field(description="被吊销的 license ID")
    revoked_at: datetime = Field(description="吊销时间（UTC ISO 8601）")
    reason: str = Field(default="", max_length=512, description="吊销原因（可空）")


class RevocationListPayload(BaseModel):
    """CRL 业务负载。Verifier 用 sequence 比较新旧 CRL，挑较新者。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    crl_version: str = Field(default=CRL_FORMAT_VERSION, description="CRL 协议版本")
    sequence: int = Field(ge=1, description="单调递增的版本序号；同一 LA 不可回退")
    issued_at: datetime = Field(description="本份 CRL 的生成时间")
    next_update_at: datetime = Field(description="LA 承诺最晚下次更新时间；Verifier 用于判定过期 CRL")
    entries: list[RevocationEntry] = Field(default_factory=list, description="吊销条目；按 license_id 字典序排序")

    def canonical_bytes(self) -> bytes:
        """规范化字节流（与 LicensePayload 同套算法）。"""
        data = self.model_dump(mode="json")
        # 确保 entries 按 license_id 排序，输入相同时产出相同字节流
        data["entries"] = sorted(data["entries"], key=lambda e: e["license_id"])
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_canonical_bytes(cls, raw: bytes) -> "RevocationListPayload":
        return cls.model_validate_json(raw.decode("utf-8"))

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

    def to_json_bytes(self) -> bytes:
        return json.dumps(
            {
                "algorithm": self.algorithm,
                "crl_format_version": self.crl_format_version,
                "key_id": self.key_id,
                "magic": self.magic,
                "signed_at": self.signed_at.astimezone(timezone.utc).isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "CrlMetadata":
        try:
            obj = json.loads(raw.decode("utf-8"))
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
    payload_canonical_bytes: bytes      # 保留原始字节用于验签
    signature: bytes
    metadata: CrlMetadata


def _add_tar_entry(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def pack_crl(payload: RevocationListPayload, signature: bytes, metadata: CrlMetadata) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_tar_entry(tar, "payload.json", payload.canonical_bytes())
        _add_tar_entry(tar, "signature.bin", signature)
        _add_tar_entry(tar, "metadata.json", metadata.to_json_bytes())
    return buf.getvalue()


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
