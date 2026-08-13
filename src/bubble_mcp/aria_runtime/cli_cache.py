"""Persistent cache boundary for the legacy Bubble CLI runtime."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from collections.abc import Callable, Mapping
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
        payload = self._read_object(self.cache_path)
        return _normalize_payload(payload)

    def _read_object(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            self._warn(f"Could not load CLI cache {path}: {exc}")
            return None
        if not isinstance(payload, dict):
            self._warn(f"Could not load CLI cache {path}: top-level JSON must be an object")
            return None
        return payload

    def save(self, payload: Mapping[str, Any]) -> bool:
        """Atomically persist a normalized payload without exposing partial JSON."""
        temporary_path: Path | None = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_path.parent,
                prefix=f".{self.cache_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(_normalize_payload(dict(payload)), handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.cache_path)
            temporary_path = None
            return True
        except (OSError, TypeError, ValueError) as exc:
            self._warn(f"Could not save CLI cache {self.cache_path}: {exc}")
            return False
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear(self) -> bool:
        """Remove the canonical cache file if present."""
        try:
            self.cache_path.unlink(missing_ok=True)
            return True
        except OSError as exc:
            self._warn(f"Could not clear CLI cache {self.cache_path}: {exc}")
            return False

    def migrate_legacy(self) -> bool:
        """Merge a legacy temp cache without overwriting canonical conflicts."""
        legacy_path = self.legacy_path
        if legacy_path is None or legacy_path == self.cache_path or not legacy_path.exists():
            return False

        legacy = self._read_object(legacy_path)
        if legacy is None:
            return False

        canonical: dict[str, Any] = {}
        if self.cache_path.exists():
            canonical = self._read_object(self.cache_path) or {}
        merged = merge_cache_payloads(legacy, canonical)
        return self.save(_normalize_payload(merged))
