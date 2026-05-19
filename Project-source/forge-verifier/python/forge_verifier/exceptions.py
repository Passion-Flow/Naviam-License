"""Verifier 异常。"""
from __future__ import annotations

from forge_verifier.types import VerificationStatus


class VerificationFailed(Exception):
    """启动期验签失败 — 业务层应捕获后 exit 1。"""

    def __init__(self, status: VerificationStatus, reason: str | None = None) -> None:
        self.status = status
        self.reason = reason
        super().__init__(f"{status}: {reason}" if reason else status)
