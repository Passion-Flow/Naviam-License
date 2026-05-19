"""Forge Verifier — Python 参考实现。

公共 API：
- Verifier：主入口类
- VerificationResult / VerificationStatus：验证结果
- VerificationFailed：验证失败异常
"""
from __future__ import annotations

from forge_verifier.exceptions import VerificationFailed
from forge_verifier.types import VerificationResult, VerificationStatus
from forge_verifier.verifier import Verifier

__all__ = [
    "Verifier",
    "VerificationResult",
    "VerificationStatus",
    "VerificationFailed",
]

__version__ = "0.1.0"
