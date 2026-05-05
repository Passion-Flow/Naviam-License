"""SDK 实例密钥的本地持久化（per crypto-spec.md §3.1）。

为什么要存：
    spec §3.1 中 hardware_fp = HMAC-SHA256(instance_pubkey, hw_inputs)。
    instance_pubkey 名为 "public" 但**实际作为 HMAC key 使用**，
    因此对攻击者而言它是机密 — 谁知道这个值，谁就能在另一台机器上伪造 hardware_fp。
    Cloud ID 中只暴露 sha256(instance_pubkey)[:16]，不暴露原值。

威胁模型：
    防御目标：
    - 攻击者拿到 *.lic + Cloud ID 文本（公开制品）后，无法在另一台机器上重建 fingerprint
    防御不到：
    - 攻击者已是同一台机器同一用户身份（rm -rf $HOME 已经够喝一壶 — 文件权限失效）
    - 攻击者拿到 root（操作系统级失守，所有用户态密钥都需要重新生成）

存储位置：
    Linux / macOS: $HOME/.naviam/license-sdk/instance.json   (0600, 父目录 0700)
    Windows     : %LOCALAPPDATA%\\Naviam\\license-sdk\\instance.json

存储格式（JSON，schema_version=1）：
    {
        "schema_version": 1,
        "instance_id":    "<base64url 32 bytes random>",
        "private_key":    "<base64 32 bytes Ed25519 private>",
        "public_key":     "<base64 32 bytes Ed25519 public>",
        "created_at":     <unix-seconds int>,
        "integrity":      "<sha256(canonical of above) hex>"
    }

不做：
    - 不上 OS keyring（Linux secret-service / macOS Keychain / Windows DPAPI）— V2 评估
    - 不引入 passphrase 加密（无地方安全存 passphrase；FS 权限已是同等强度）
    - 不实现 HSM / TPM 集成（V2/V3）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .errors import LicenseSDKError

_SCHEMA_VERSION = 1
_FILE_NAME = "instance.json"


# === 数据模型 ===


@dataclass(frozen=True)
class Keypair:
    """SDK 实例的密钥三元组。线程安全：实例不可变。"""

    instance_id: bytes      # 32 字节随机；Cloud ID 中作为 "instance_id" 字段
    private_key: bytes      # Ed25519 32 字节私钥（用于 mTLS / 未来签名）
    public_key: bytes       # Ed25519 32 字节公钥；同时作为 hardware_fp 的 HMAC key
    created_at: int         # 创建时刻 unix-seconds


# === 路径解析 ===


def default_keystore_dir() -> Path:
    """跨平台默认密钥目录。"""
    sysname = platform.system()
    if sysname == "Windows":
        # %LOCALAPPDATA% 总是用户级、不漫游、不被 OneDrive 同步
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "Naviam" / "license-sdk"
        return Path.home() / "AppData" / "Local" / "Naviam" / "license-sdk"
    # Linux / macOS：用 ~/.naviam — 与隐藏文件惯例一致
    return Path.home() / ".naviam" / "license-sdk"


def default_keystore_path() -> Path:
    return default_keystore_dir() / _FILE_NAME


# === 序列化辅助 ===


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _integrity_payload(data: dict[str, Any]) -> bytes:
    """对除 integrity 字段外的内容做规范化哈希。

    用 sorted-keys JSON 而不是 CBOR 是因为 keystore 文件需要在 Windows
    notepad 之类工具可读；调试友好优先于体积。
    """
    payload = {k: data[k] for k in data if k != "integrity"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def _integrity_hex(data: dict[str, Any]) -> str:
    return _integrity_payload(data).hex()


# === FS 权限收紧（POSIX） ===


def _harden_perms(path: Path) -> None:
    """文件 0600，父目录 0700。Windows 上仅记 warning（NTFS ACL 由 OS 默认 ACL 管理）。"""
    if os.name == "nt":
        return  # Windows: chmod 不是真权限模型；用户级目录已隔离
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)            # 0600
        path.parent.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)  # 0700
    except (OSError, PermissionError):
        # 已是软化降级；不阻断 SDK 启动 — 调用方可以选择审计
        pass


def _check_perms(path: Path) -> None:
    """启动时回查文件模式：若世界可读，抛错（防"配置漂移"）。"""
    if os.name == "nt":
        return
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return
    if mode & 0o077:  # 任意 group/other 权限位
        raise LicenseSDKError(
            f"keystore file {path} has insecure mode {oct(mode)}; "
            "must be 0600 (chmod 600 the file or remove and regenerate)"
        )


# === 主 API ===


def load_or_create_keypair(path: str | Path | None = None) -> Keypair:
    """加载已有密钥；不存在则生成 + 持久化。

    返回的 Keypair 实例可被多次复用（不可变）。线程安全：写入只发生在初次调用；
    并发调用首次创建可能产生竞争 — 调用方应在进程启动期单次调用。
    """
    p = Path(path) if path is not None else default_keystore_path()

    if p.exists():
        _check_perms(p)
        return _load(p)

    keypair = _generate()
    p.parent.mkdir(parents=True, exist_ok=True)
    _save(p, keypair)
    _harden_perms(p)  # 内部同时把父目录设 0700
    return keypair


def _generate() -> Keypair:
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    return Keypair(
        instance_id=secrets.token_bytes(32),
        private_key=sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        public_key=pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
        created_at=int(time.time()),
    )


def _save(path: Path, kp: Keypair) -> None:
    data: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "instance_id": _b64(kp.instance_id),
        "private_key": _b64(kp.private_key),
        "public_key":  _b64(kp.public_key),
        "created_at":  kp.created_at,
    }
    data["integrity"] = _integrity_hex(data)
    # 原子写：先写 .tmp，再 rename
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, sort_keys=True, separators=(",", ":"), indent=None),
        encoding="utf-8",
    )
    _harden_perms(tmp)
    tmp.replace(path)


def _load(path: Path) -> Keypair:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, PermissionError) as exc:
        raise LicenseSDKError(f"keystore unreadable: {path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LicenseSDKError(f"keystore not valid JSON: {path}") from exc

    if not isinstance(data, dict):
        raise LicenseSDKError(f"keystore root not an object: {path}")

    schema = data.get("schema_version")
    if schema != _SCHEMA_VERSION:
        raise LicenseSDKError(
            f"keystore schema_version={schema!r} not supported; expected {_SCHEMA_VERSION}"
        )

    # 完整性校验（防工具误改 / 部分写入）
    stored = data.get("integrity")
    if not isinstance(stored, str):
        raise LicenseSDKError("keystore missing integrity field")
    expected = _integrity_hex(data)
    if not hmac.compare_digest(stored, expected):
        raise LicenseSDKError(
            "keystore integrity mismatch — file was modified outside SDK; "
            "delete and regenerate, but note: hardware_fp will change → license rebind required"
        )

    try:
        return Keypair(
            instance_id=_b64d(data["instance_id"]),
            private_key=_b64d(data["private_key"]),
            public_key=_b64d(data["public_key"]),
            created_at=int(data["created_at"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise LicenseSDKError(f"keystore field decode failed: {exc}") from exc


def reset_keystore(path: str | Path | None = None) -> None:
    """删除密钥文件 — 下次 load_or_create_keypair 会重新生成。

    谨慎：删除后 SDK 实例的 hardware_fp 会变，已签发的 License 失效。
    一般仅在硬件更换 / 实例迁移时调用。
    """
    p = Path(path) if path is not None else default_keystore_path()
    if p.exists():
        p.unlink()
