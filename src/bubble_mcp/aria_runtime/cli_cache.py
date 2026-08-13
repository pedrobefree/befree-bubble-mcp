"""Persistent cache boundary for the legacy Bubble CLI runtime."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


WarnCallback = Callable[[str], None]


def default_cache_payload() -> dict[str, Any]:
    """Return a fresh canonical Bubble CLI cache payload."""
    return {
        "colors": {},
        "fonts": {},
        "styles": {},
        "components": {},
        "schema": {"profiles": {}},
    }


def merge_cache_payloads(base: Any, incoming: Any) -> Any:
    """Recursively merge payloads, preferring non-null incoming values."""
    if isinstance(base, dict) and isinstance(incoming, dict):
        merged = copy.deepcopy(base)
        for key, value in incoming.items():
            if key in merged:
                merged[key] = merge_cache_payloads(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(incoming if incoming is not None else base)


def _normalize_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return default_cache_payload()

    normalized = copy.deepcopy(payload)
    for bucket in ("colors", "fonts", "styles", "components"):
        if not isinstance(normalized.get(bucket), dict):
            normalized[bucket] = {}

    schema = normalized.get("schema")
    if not isinstance(schema, dict):
        schema = {}
        normalized["schema"] = schema
    if not isinstance(schema.get("profiles"), dict):
        schema["profiles"] = {}
    return normalized


class BubbleCLICacheStore:
    """Read and normalize a Bubble CLI JSON cache file."""

    def __init__(
        self,
        cache_path: str | os.PathLike[str],
        *,
        legacy_path: str | os.PathLike[str] | None = None,
        warn: WarnCallback | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.legacy_path = Path(legacy_path) if legacy_path is not None else None
        self._warn = warn or (lambda _message: None)

    def load(self) -> dict[str, Any]:
        """Return normalized cache data, or defaults when the file is unusable."""
        if not self.cache_path.exists():
            return default_cache_payload()
        try:
            with self.cache_path.open("r", encoding="utf-8") as handle:
                return _normalize_payload(json.load(handle))
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            self._warn(f"Could not load CLI cache {self.cache_path}: {exc}")
            return default_cache_payload()
