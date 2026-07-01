"""Utilities for redacting sensitive values from logs and reports."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEY_PATTERN = re.compile(
    r"(authorization|bearer|cookie|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|secret|password|private[_-]?key|token)",
    re.IGNORECASE,
)

SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{12,}\b"),
]


def redact_string(value: str) -> str:
    """Redact secret-like substrings from a string."""

    redacted = value
    for pattern in SENSITIVE_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_sensitive(value: Any) -> Any:
    """Recursively redact secret-like keys and values."""

    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_PATTERN.search(key_text):
                output[key_text] = "[REDACTED]"
            else:
                output[key_text] = redact_sensitive(child)
        return output
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return redact_string(value)
    return value
