"""binding=hard — 签发时硬绑指纹，Verifier 每次启动严格比对。

特性：
- payload.bound_fingerprint 在 LA 签发时写入，签名保护，不可篡改
- 启动期采集当前指纹，与 bound_fingerprint 用 hmac.compare_digest 比对
- 不一致直接拒绝（不留宽容；hard 就要硬）

安全性：
- 攻击者把 license 拷到另一台机器：指纹不同 → 拒绝
- 攻击者重写 payload.bound_fingerprint：签名失效 → 拒绝
- 攻击者重新生成密钥再签：公钥不匹配 → 拒绝
"""
from __future__ import annotations

import hmac
from pathlib import Path

from forge_verifier.binding.policy import BindingCheckResult, BindingPolicy
from forge_verifier.fingerprint import collect_fingerprint
from forge_verifier.parsing import ForgeFile


class HardBindingPolicy:
    name = "hard"

    def check(
        self,
        *,
        forge: ForgeFile,
        state_dir: Path,  # noqa: ARG002 — hard 不需要状态
        fingerprint_override: str | None = None,
    ) -> BindingCheckResult:
        bound = forge.payload.bound_fingerprint
        if not bound:
            return BindingCheckResult(
                passed=False,
                current_fingerprint="",
                expected_fingerprint=None,
                reason="hard binding requires bound_fingerprint in payload",
            )

        current = collect_fingerprint(override=fingerprint_override)
        if hmac.compare_digest(current, bound):
            return BindingCheckResult(
                passed=True,
                current_fingerprint=current,
                expected_fingerprint=bound,
            )
        return BindingCheckResult(
            passed=False,
            current_fingerprint=current,
            expected_fingerprint=bound,
            reason="deployment fingerprint mismatch",
        )
