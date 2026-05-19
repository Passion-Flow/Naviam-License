"""Binding policies — none / soft / hard。

每档 binding 是一个独立模块（与全局"每个独立功能一个目录"细分原则一致）。
通过 get_binding_policy(...) 工厂按 payload.binding 字段路由。
"""
from __future__ import annotations

from forge_verifier.binding.policy import BindingCheckResult, BindingPolicy


def get_binding_policy(binding: str) -> BindingPolicy:
    if binding == "none":
        from forge_verifier.binding.none.policy import NoneBindingPolicy
        return NoneBindingPolicy()
    if binding == "soft":
        from forge_verifier.binding.soft.policy import SoftBindingPolicy
        return SoftBindingPolicy()
    if binding == "hard":
        from forge_verifier.binding.hard.policy import HardBindingPolicy
        return HardBindingPolicy()
    raise ValueError(f"Unsupported binding mode: {binding!r}")


__all__ = ["BindingCheckResult", "BindingPolicy", "get_binding_policy"]
