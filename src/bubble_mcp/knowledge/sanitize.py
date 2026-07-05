"""Sanitize documentation queries before any future remote docs lookup."""

from __future__ import annotations

import re


_AUTH_PATTERNS = (
    re.compile(r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"\bAuthorization\s+Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
)
_CLIENT_SECRET_PATTERNS = (
    re.compile(r"\bclient[_-]?id\s*[:=]\s*[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"\bclient\s+id\s*:?\s*[A-Za-z0-9._-]+", re.IGNORECASE),
)
_CLIENT_ID_CONTEXT_PATTERN = re.compile(
    r"\b(?P<label>app|client|customer|project)\s+(?P<id>[a-z0-9]+(?:-[a-z0-9]+){2,})\b",
    re.IGNORECASE,
)
_OPAQUE_TOKEN_PATTERN = re.compile(r"\b(?=[A-Za-z0-9._]{24,}\b)(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9._]+\b")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def sanitize_remote_docs_query(query: str) -> str:
    """Remove project-sensitive values while preserving general documentation topics."""

    sanitized = str(query or "")
    for pattern in _AUTH_PATTERNS:
        sanitized = pattern.sub(" ", sanitized)
    for pattern in _CLIENT_SECRET_PATTERNS:
        sanitized = pattern.sub(" ", sanitized)
    sanitized = _CLIENT_ID_CONTEXT_PATTERN.sub(lambda match: match.group("label"), sanitized)
    sanitized = _OPAQUE_TOKEN_PATTERN.sub(" ", sanitized)
    return _WHITESPACE_PATTERN.sub(" ", sanitized).strip()
