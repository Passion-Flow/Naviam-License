"""Audit-write contract shared across modules.

每个 service 函数在状态变更前后必须调用 audit.append(...)，详见 docs/security/crypto-spec.md。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    actor_id: str | None
    actor_kind: str
    actor_ip: str | None
    action: str
    target_kind: str | None
    target_id: str | None
    request_id: str | None
    payload: dict[str, Any]
