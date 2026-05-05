"""Cloud ID v1 编解码。

编码：CBOR -> SHA-256 前 4 字节 checksum -> base32 -> 每 6 字符加 '-'。
解码：逆序；校验 checksum、字段、时间偏差。

关于 Cloud ID 与 License 绑定：
    Cloud ID 内含两类字段：
      - 机器特征类（绑定指纹）：schema_version / product_code / instance_id /
        instance_pubkey_fp / hardware_fp —— 这些字段同一台机器多次生成 Cloud ID 时
        必须保持不变；它们才是"License 不可复制"的根。
      - 新鲜度类（每次随机/实时）：nonce / created_at —— 用于防重放和时钟检查，
        每次生成都不同，**绝不能进入 License 的 cloud_id_binding**。

    因此 License payload['cloud_id_binding'] 存放的不是整段 Cloud ID 文本，而是
    binding fingerprint：sha256(canonical_CBOR(subset_of_BINDING_FIELDS)) — 32 字节。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from datetime import datetime, timezone
from typing import Any

import cbor2


class CloudIDError(ValueError):
    """Cloud ID 解码或校验失败。"""


# 字段名常量（canonical CBOR map key order）
_CLOUD_ID_FIELDS = [
    "schema_version",
    "product_code",
    "instance_id",
    "instance_pubkey_fp",
    "hardware_fp",
    "nonce",
    "created_at",
]

# License 绑定指纹仅取以下"机器特征"字段；nonce/created_at 必须排除。
# 修改本列表 = 破坏向前兼容；任何变更必须升 schema_version。
_BINDING_FIELDS: tuple[str, ...] = (
    "schema_version",
    "product_code",
    "instance_id",
    "instance_pubkey_fp",
    "hardware_fp",
)


def _checksum(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()[:4]


def _base32_encode(data: bytes) -> str:
    # 标准 base32 大写，去掉尾部 '='
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _base32_decode(text: str) -> bytes:
    # 补回 padding
    pad = 8 - (len(text) % 8)
    if pad != 8:
        text += "=" * pad
    return base64.b32decode(text, casefold=True)


def _group(text: str, size: int = 6) -> str:
    return "-".join(text[i : i + size] for i in range(0, len(text), size))


def _ungroup(text: str) -> str:
    return text.replace("-", "").replace(" ", "").upper()


def encode(cloud_id_map: dict[str, Any]) -> str:
    """将 Cloud ID 字典编码为人类可读字符串。"""
    canonical = cbor2.dumps(cloud_id_map, canonical=True)
    cs = _checksum(canonical)
    b32 = _base32_encode(canonical + cs)
    return _group(b32)


def decode(text: str, *, max_age_seconds: int = 600, now: datetime | None = None) -> dict[str, Any]:
    """解码并校验 Cloud ID。

    失败时抛 CloudIDError。
    """
    text = _ungroup(text)
    if len(text) < 8:
        raise CloudIDError("too short")

    try:
        raw = _base32_decode(text)
    except Exception as exc:
        raise CloudIDError(f"base32 decode failed: {exc}") from exc

    if len(raw) < 5:
        raise CloudIDError("decoded too short")

    payload = raw[:-4]
    expected_cs = raw[-4:]
    actual_cs = _checksum(payload)
    if not _constant_time_compare(expected_cs, actual_cs):
        raise CloudIDError("checksum mismatch")

    try:
        obj = cbor2.loads(payload)
    except Exception as exc:
        raise CloudIDError(f"cbor decode failed: {exc}") from exc

    if not isinstance(obj, dict):
        raise CloudIDError("root is not a map")

    _validate_fields(obj)
    _validate_timestamps(obj, max_age_seconds=max_age_seconds, now=now)
    return obj


def _validate_fields(obj: dict[str, Any]) -> None:
    if int(obj.get("schema_version", 0)) != 1:
        raise CloudIDError("unsupported schema_version")
    if len(obj.get("instance_pubkey_fp", b"")) != 16:
        raise CloudIDError("instance_pubkey_fp must be 16 bytes")
    if len(obj.get("hardware_fp", b"")) != 32:
        raise CloudIDError("hardware_fp must be 32 bytes")
    if len(obj.get("nonce", b"")) != 16:
        raise CloudIDError("nonce must be 16 bytes")


def _validate_timestamps(
    obj: dict[str, Any],
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    created_at = int(obj.get("created_at", 0))
    server_ts = int(now.timestamp())
    if abs(server_ts - created_at) > max_age_seconds:
        raise CloudIDError("created_at too far from server time")


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    """常量时间比较；标准做法用 hmac.compare_digest（Bug 5 修复）。"""
    return hmac.compare_digest(a, b)


def binding_fingerprint(cloud_id_text_or_dict: str | dict[str, Any]) -> bytes:
    """计算 Cloud ID 的 32 字节 binding fingerprint。

    fingerprint = sha256( canonical_CBOR( {k: cloud_id[k] for k in _BINDING_FIELDS} ) )

    用法：
      - 签发时（issuer）：把它写入 License payload['cloud_id_binding']
      - 校验时（SDK）：从运行期 Cloud ID 计算同一份 fingerprint，与 payload 内的
        fingerprint 用 hmac.compare_digest 比较

    入参可以是 Cloud ID 文本（带分组横线）或已解码的 dict。
    """
    if isinstance(cloud_id_text_or_dict, str):
        obj = decode(cloud_id_text_or_dict, max_age_seconds=_FINGERPRINT_NO_TIME_CHECK)
    elif isinstance(cloud_id_text_or_dict, dict):
        obj = cloud_id_text_or_dict
    else:
        raise CloudIDError(f"expected str or dict, got {type(cloud_id_text_or_dict).__name__}")

    try:
        subset = {k: obj[k] for k in _BINDING_FIELDS}
    except KeyError as exc:
        raise CloudIDError(f"cloud_id missing field: {exc.args[0]!r}") from exc

    canonical = cbor2.dumps(subset, canonical=True)
    return hashlib.sha256(canonical).digest()


# 用于 binding_fingerprint 内部解码：fingerprint 计算时不应做时间偏差检查
# （License 续期时可能离 Cloud ID 创建时刻很远）
_FINGERPRINT_NO_TIME_CHECK = 10**12
