"""SDK 端 Cloud ID 解析与 binding fingerprint 计算。

故意与后端 src/modules/activations/cloud_id_codec.py 重复实现 — SDK 不能依赖后端代码。
两边的协议完全一致：

    fingerprint = sha256( canonical_CBOR( {k: cloud_id[k] for k in _BINDING_FIELDS} ) )

绑定字段 = 同一台机器多次生成 Cloud ID 时**应当稳定**的字段；
排除字段 = nonce / created_at（每次随机/实时，不能进入绑定）。

校验时：
    1. 调用方提供运行期 Cloud ID 文本（每次启动可重新生成，nonce/created_at 不同）
    2. SDK 内部解码 → 取 _BINDING_FIELDS 子集 → CBOR canonical → SHA-256 → 32 字节
    3. 与 license payload['cloud_id_binding']（也是 32 字节）用 hmac.compare_digest 比

License 复制到另一台机器后，新机器的 hardware_fp/instance_pubkey_fp 会变 → fingerprint
会不一样 → CloudIDMismatch。这就是"License 不可复制"的真正落点。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

import cbor2

from .errors import CloudIDMismatch, LicenseSDKError

# 与后端 _BINDING_FIELDS 完全一致；任何修改 = 协议破坏 = 必须升 schema_version
_BINDING_FIELDS: tuple[str, ...] = (
    "schema_version",
    "product_code",
    "instance_id",
    "instance_pubkey_fp",
    "hardware_fp",
)


def _ungroup(text: str) -> str:
    """去掉分组横线 / 空格，统一大写。"""
    return text.replace("-", "").replace(" ", "").upper()


def _base32_decode(text: str) -> bytes:
    pad = (-len(text)) % 8
    return base64.b32decode(text + ("=" * pad), casefold=True)


def _checksum(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()[:4]


def decode_cloud_id_text(text: str) -> dict[str, Any]:
    """解码 Cloud ID 文本为 dict。

    校验 base32 + checksum + map 结构；不做时间偏差检查（计算 fingerprint 时
    时间无关；时间偏差只在 issuer 端激活路径上做）。
    """
    if not isinstance(text, str):
        raise LicenseSDKError(f"cloud_id must be str, got {type(text).__name__}")

    s = _ungroup(text)
    if len(s) < 8:
        raise LicenseSDKError("cloud_id too short")

    try:
        raw = _base32_decode(s)
    except Exception as exc:
        raise LicenseSDKError(f"cloud_id base32 decode failed: {exc}") from exc

    if len(raw) < 5:
        raise LicenseSDKError("cloud_id decoded too short")

    payload = raw[:-4]
    expected_cs = raw[-4:]
    actual_cs = _checksum(payload)
    if not hmac.compare_digest(expected_cs, actual_cs):
        raise LicenseSDKError("cloud_id checksum mismatch")

    try:
        obj = cbor2.loads(payload)
    except cbor2.CBORDecodeError as exc:
        raise LicenseSDKError(f"cloud_id cbor decode failed: {exc}") from exc

    if not isinstance(obj, dict):
        raise LicenseSDKError("cloud_id root is not a CBOR map")

    return obj


def binding_fingerprint(cloud_id: str | dict[str, Any]) -> bytes:
    """计算 32 字节 binding fingerprint。入参可为 Cloud ID 文本或已解码 dict。"""
    if isinstance(cloud_id, str):
        obj = decode_cloud_id_text(cloud_id)
    elif isinstance(cloud_id, dict):
        obj = cloud_id
    else:
        raise LicenseSDKError(
            f"cloud_id must be str or dict, got {type(cloud_id).__name__}"
        )

    try:
        subset = {k: obj[k] for k in _BINDING_FIELDS}
    except KeyError as exc:
        raise LicenseSDKError(f"cloud_id missing field: {exc.args[0]!r}") from exc

    canonical = cbor2.dumps(subset, canonical=True)
    return hashlib.sha256(canonical).digest()


def assert_binding_matches(
    payload_cloud_id_binding: Any,
    runtime_cloud_id: str | dict[str, Any],
) -> None:
    """SDK validator 调用：把 payload 内 32 字节 fingerprint 与运行期算出的对比。

    任何不一致都抛 CloudIDMismatch。"""
    if not isinstance(payload_cloud_id_binding, (bytes, bytearray, memoryview)):
        raise CloudIDMismatch(
            f"payload cloud_id_binding must be bytes, got "
            f"{type(payload_cloud_id_binding).__name__}"
        )
    payload_fp = bytes(payload_cloud_id_binding)
    if len(payload_fp) != 32:
        raise CloudIDMismatch(
            f"payload cloud_id_binding must be 32 bytes (sha-256), got {len(payload_fp)}"
        )

    runtime_fp = binding_fingerprint(runtime_cloud_id)
    if not hmac.compare_digest(payload_fp, runtime_fp):
        raise CloudIDMismatch("license cloud_id_binding != runtime fingerprint")
