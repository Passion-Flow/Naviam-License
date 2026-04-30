"""Structured JSON logger.

阶段 1 实现：以 JSON 行格式输出，过滤敏感字段（password / passphrase / secret / token / cookie）。
"""
from __future__ import annotations

import json
import logging

REDACT_KEYS = frozenset({"password", "passphrase", "secret", "token", "cookie", "csrf"})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(_redact(payload), ensure_ascii=False)


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            k: ("***" if k.lower() in REDACT_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value
