"""Binding policy 统一接口。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from forge_verifier.parsing import ForgeFile


@dataclass(frozen=True, slots=True)
class BindingCheckResult:
    """binding 校验结果。"""

    passed: bool
    current_fingerprint: str
    expected_fingerprint: str | None = None
    reason: str | None = None


class BindingPolicy(Protocol):
    """统一接口；每档 binding 实现"启动期 + 后续复查"两个钩子。"""

    @property
    def name(self) -> str: ...

    def check(
        self,
        *,
        forge: ForgeFile,
        state_dir: Path,
        fingerprint_override: str | None = None,
    ) -> BindingCheckResult:
        """对当前环境做 binding 检查。

        Args:
            forge: 已解包的 .forge 内容（含 payload.binding / bound_fingerprint）
            state_dir: Verifier 本地状态目录（soft/hard 都需要）；不存在则自动创建
            fingerprint_override: 测试 / 客户显式覆盖（一般为 None）
        """
        ...
