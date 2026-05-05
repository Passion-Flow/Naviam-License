"""跨平台硬件特征收集（per crypto-spec.md §3.1）。

输出：
    inputs = collect_hardware_inputs() -> dict[str, str]
    hardware_fp = HMAC-SHA256(instance_pubkey, normalize(inputs))

设计原则：
1. **故障软化**：单一硬件信号缺失不拒绝服务（容器、虚拟机场景常见）。
2. **不存原始数据**：所有原始硬件信息只在内存里走一趟，最终输出只是 HMAC 结果。
3. **稳定性优先**：选择那些"同一台物理机重启后保持不变"的字段；CPU 频率 /
   网络 IP / 进程 PID 这种波动信号一律不用。
4. **零第三方依赖**：仅 stdlib + subprocess（不引入 psutil / dmidecode-py / wmi）。
5. **subprocess 调用全部带超时**：避免恶意硬件让 SDK 启动挂死。

字段优先级（同一台机器至少有 2 项命中即可获得稳定 fingerprint）：
- machine_id：OS 级唯一标识（Linux /etc/machine-id；macOS IOPlatformUUID；Windows SMBIOS）
- cpu_model：CPU 型号字符串（norm 后）
- mainboard_serial：主板/系统序列号
- disk_serial：第一块系统盘序列号

容器环境：machine_id 通常是宿主或镜像 baked，cpu_model 仍准确，mainboard 通常拿不到 —
两个稳定信号已足够生成 fingerprint；这是设计上的权衡，不是 bug。
"""
from __future__ import annotations

import hashlib
import hmac
import platform
import re
import subprocess
from pathlib import Path
from typing import Callable

from .errors import LicenseSDKError

_SUBPROCESS_TIMEOUT_S = 3.0  # 每条命令上限 3 秒；累计上限 ~12 秒


# === 平台无关辅助 ===


def _run(cmd: list[str], *, timeout: float = _SUBPROCESS_TIMEOUT_S) -> str | None:
    """运行命令，返回 stdout 文本；任何错误（含超时、找不到命令）返回 None。"""
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def _normalize(s: str) -> str:
    """折叠空白、去掉末尾换行、统一小写 — 让"Intel(R) Xeon"和"intel(r)  xeon"被视作相同。"""
    return " ".join(s.lower().split())


def _read_text(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, PermissionError):
        return None


# === 各平台采集器 ===


def _linux() -> dict[str, str]:
    inputs: dict[str, str] = {}

    # machine_id (systemd) 或 dbus
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        v = _read_text(path)
        if v:
            inputs["machine_id"] = v
            break

    # CPU 型号
    cpuinfo = _read_text("/proc/cpuinfo")
    if cpuinfo:
        m = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
        if m:
            inputs["cpu_model"] = _normalize(m.group(1))

    # 主板序列号 / 系统 UUID（dmidecode 通常需要 root）
    for cmd in (
        ["cat", "/sys/class/dmi/id/product_uuid"],
        ["cat", "/sys/class/dmi/id/board_serial"],
        ["dmidecode", "-s", "system-uuid"],
    ):
        v = _run(cmd)
        if v and v.strip() and v.strip().lower() != "unknown":
            inputs["mainboard_serial"] = v.strip()
            break

    # 第一块物理盘的序列号
    out = _run(["lsblk", "-ndo", "NAME,SERIAL", "-x", "NAME"])
    if out:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] and not parts[0].startswith("loop"):
                inputs["disk_serial"] = parts[1]
                break

    return inputs


def _macos() -> dict[str, str]:
    inputs: dict[str, str] = {}

    out = _run(["ioreg", "-d2", "-c", "IOPlatformExpertDevice"])
    if out:
        m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
        if m:
            inputs["machine_id"] = m.group(1)
        m = re.search(r'"IOPlatformSerialNumber"\s*=\s*"([^"]+)"', out)
        if m:
            inputs["mainboard_serial"] = m.group(1)

    out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    if out and out.strip():
        inputs["cpu_model"] = _normalize(out)

    # 系统盘 (rootfs) 序列号
    out = _run(["diskutil", "info", "/"])
    if out:
        m = re.search(r"Volume UUID:\s+([0-9A-F-]+)", out)
        if m:
            inputs["disk_serial"] = m.group(1)

    return inputs


def _windows() -> dict[str, str]:
    inputs: dict[str, str] = {}

    # WMI via PowerShell；避免引入 pywin32
    def _wmi(klass: str, prop: str) -> str | None:
        out = _run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"(Get-WmiObject -Class {klass}).{prop}",
            ]
        )
        return out.strip() if out else None

    v = _wmi("Win32_ComputerSystemProduct", "UUID")
    if v:
        inputs["machine_id"] = v

    v = _wmi("Win32_Processor", "Name")
    if v:
        inputs["cpu_model"] = _normalize(v)

    v = _wmi("Win32_BaseBoard", "SerialNumber")
    if v and v.lower() not in ("none", "default string", "to be filled by o.e.m."):
        inputs["mainboard_serial"] = v

    out = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-WmiObject -Class Win32_DiskDrive | Where-Object Index -eq 0).SerialNumber",
        ]
    )
    if out and out.strip():
        inputs["disk_serial"] = out.strip()

    return inputs


_COLLECTORS: dict[str, Callable[[], dict[str, str]]] = {
    "Linux": _linux,
    "Darwin": _macos,
    "Windows": _windows,
}


# === 公开 API ===


def collect_hardware_inputs() -> dict[str, str]:
    """返回 OS 上能采集到的硬件特征字段（小写、规范化）。

    至少需要 2 项命中才认为足够稳定；不足时仍返回（调用方决定是否拒绝）。
    """
    sysname = platform.system()
    collector = _COLLECTORS.get(sysname)
    if collector is None:
        # 兜底：只能用 platform 层信息（容器内、未知 OS）
        return {
            "cpu_model": _normalize(platform.processor() or platform.machine()),
            "platform": _normalize(f"{sysname} {platform.release()}"),
        }

    inputs = collector()
    # 兜底字段，确保哪怕 OS 命令全失败也有可哈希内容
    if "cpu_model" not in inputs:
        cpu = platform.processor() or platform.machine()
        if cpu:
            inputs["cpu_model"] = _normalize(cpu)
    return inputs


def hardware_fp(
    instance_pubkey: bytes,
    *,
    inputs: dict[str, str] | None = None,
    min_signals: int = 2,
) -> bytes:
    """计算 32 字节 hardware_fp = HMAC-SHA256(instance_pubkey, canonical_inputs)。

    canonical_inputs：按 key 字典序拼接 "key=value" 用 "\\n" 分隔；同一台机器
    多次调用必须字节级一致。

    入参 instance_pubkey：32 字节 Ed25519 公钥（HMAC 的 key）。
    入参 inputs：可注入硬件输入字典；用于测试 / 容器环境用预收集值。
    入参 min_signals：至少多少个非空字段（默认 2）；不达标抛 LicenseSDKError。

    本函数与 docs/security/crypto-spec.md §3.1 公式精确对齐。
    """
    if not isinstance(instance_pubkey, (bytes, bytearray)):
        raise LicenseSDKError(
            f"instance_pubkey must be bytes, got {type(instance_pubkey).__name__}"
        )
    if len(instance_pubkey) != 32:
        raise LicenseSDKError(
            f"instance_pubkey must be 32 bytes (Ed25519 pubkey), got {len(instance_pubkey)}"
        )

    raw = inputs if inputs is not None else collect_hardware_inputs()
    non_empty = {k: v for k, v in raw.items() if v}

    if len(non_empty) < min_signals:
        raise LicenseSDKError(
            f"insufficient hardware signals: only {len(non_empty)} collected "
            f"(need ≥ {min_signals}); fields: {list(non_empty)}"
        )

    canonical = "\n".join(f"{k}={non_empty[k]}" for k in sorted(non_empty)).encode("utf-8")
    return hmac.new(instance_pubkey, canonical, hashlib.sha256).digest()
