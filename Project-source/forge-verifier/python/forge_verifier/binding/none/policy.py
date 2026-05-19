"""binding=none — 不做环境绑定，仅依赖签名 + 过期 + 服务端吊销。"""
from __future__ import annotations

from pathlib import Path

from forge_verifier.binding.policy import BindingCheckResult, BindingPolicy
from forge_verifier.fingerprint import collect_fingerprint
from forge_verifier.parsing import ForgeFile


class NoneBindingPolicy:
    name = "none"

    def check(
        self,
        *,
        forge: ForgeFile,
        state_dir: Path,  # noqa: ARG002 — none 不需要状态
        fingerprint_override: str | None = None,
    ) -> BindingCheckResult:
        # 仍采集指纹以便上报心跳，但不参与 pass/fail 判定
        current = collect_fingerprint(override=fingerprint_override)
        return BindingCheckResult(passed=True, current_fingerprint=current)
