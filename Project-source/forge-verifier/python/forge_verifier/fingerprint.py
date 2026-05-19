"""部署指纹采集 — 防 license 跨环境复制的核心。

策略（按优先级，第一个能拿到的就用）：
1. Linux:   /etc/machine-id   /  /var/lib/dbus/machine-id
2. macOS:   `ioreg -d2 -c IOPlatformExpertDevice` 取 IOPlatformUUID
3. Windows: HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid（如可读）
4. 兜底：   hostname + 主网卡 MAC（uuid.getnode），稳定性次于上者

容器场景：
- Docker 默认会把宿主 /etc/machine-id 透出到容器；客户私有化时一般 OK
- 若客户走 K8s + namespace 隔离，可能多容器同 machine-id；建议 binding=soft
  + 配合 deployment_uid（环境变量 FORGE_DEPLOYMENT_UID 覆盖）

最终输出：
- raw 字符串归一化后 SHA-256，得到固定长度的 hex 指纹
- 多源拼接顺序固定，保证同环境得到同指纹
"""
from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
import uuid
from pathlib import Path


def collect_fingerprint(*, override: str | None = None) -> str:
    """采集当前进程所在部署的指纹。

    Args:
        override: 客户可通过环境变量 FORGE_DEPLOYMENT_UID 显式指定指纹源。
                  覆盖时仍要走归一化 + SHA-256，保证格式与默认采集一致。
    """
    override = override or os.environ.get("FORGE_DEPLOYMENT_UID")
    if override:
        return _normalize(("override", override.strip()))

    sources: list[tuple[str, str]] = []

    machine_id = _read_machine_id()
    if machine_id:
        sources.append(("machine_id", machine_id))

    platform_uid = _read_platform_uid()
    if platform_uid:
        sources.append(("platform_uid", platform_uid))

    # 兜底：getnode 一定有值（MAC 失败时返回 random 48-bit，但同一进程稳定）
    sources.append(("hostname", platform.node()))
    sources.append(("mac", f"{uuid.getnode():012x}"))

    return _normalize(*sources)


def _normalize(*sources: tuple[str, str]) -> str:
    """把 (name, value) 元组拼成稳定字符串后 SHA-256。

    格式：sha256(name1=value1\\nname2=value2\\n...)，便于人审看也便于 LA 端复算。
    """
    joined = "\n".join(f"{name}={value}" for name, value in sources)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _read_machine_id() -> str | None:
    """Linux 上读 /etc/machine-id 或备用路径。"""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            content = Path(path).read_text(encoding="ascii").strip()
            if content:
                return content
        except (OSError, UnicodeDecodeError):
            continue
    return None


def _read_platform_uid() -> str | None:
    """macOS / Windows 平台 UID。"""
    system = sys.platform
    if system == "darwin":
        return _read_macos_ioreg_uuid()
    if system == "win32":
        return _read_windows_machine_guid()
    return None


def _read_macos_ioreg_uuid() -> str | None:
    try:
        out = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode != 0:
            return None
        for line in out.stdout.splitlines():
            if "IOPlatformUUID" in line:
                # 形如：  "IOPlatformUUID" = "ABCDEF12-3456-...-9999"
                _, _, value = line.partition("=")
                value = value.strip().strip('"').strip()
                if value:
                    return value
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return None


def _read_windows_machine_guid() -> str | None:  # pragma: no cover — 非 Windows 不跑
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except OSError:
        return None
