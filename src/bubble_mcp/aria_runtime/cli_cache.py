"""Persistent cache boundary for the legacy Bubble CLI runtime."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


WarnCallback = Callable[[str], None]
MutationCallback = Callable[[dict[str, Any]], bool]


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
    """Recursively merge payloads, preferring incoming values, including null."""
    if isinstance(base, dict) and isinstance(incoming, dict):
        merged = copy.deepcopy(base)
        for key, value in incoming.items():
            if key in merged:
                merged[key] = merge_cache_payloads(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(incoming)


def cache_payloads_equal(left: Any, right: Any) -> bool:
    """Compare JSON-shaped values without conflating booleans and numbers."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(
            cache_payloads_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            cache_payloads_equal(left_value, right_value)
            for left_value, right_value in zip(left, right)
        )
    return type(left) is type(right) and left == right


def apply_cache_delta(base: Any, pending: Any, latest: Any) -> Any:
    """Apply local changes from base→pending onto the latest shared payload."""
    if not isinstance(base, Mapping) or not isinstance(pending, Mapping):
        return copy.deepcopy(pending)

    reconciled = copy.deepcopy(dict(latest)) if isinstance(latest, Mapping) else {}
    for key in base:
        if key not in pending:
            reconciled.pop(key, None)
    for key, pending_value in pending.items():
        if key not in base:
            latest_value = reconciled.get(key)
            if isinstance(pending_value, Mapping) and isinstance(latest_value, Mapping):
                reconciled[key] = apply_cache_delta({}, pending_value, latest_value)
            else:
                reconciled[key] = copy.deepcopy(pending_value)
            continue
        base_value = base[key]
        if cache_payloads_equal(pending_value, base_value):
            continue
        latest_value = reconciled.get(key)
        if isinstance(pending_value, Mapping) and isinstance(latest_value, Mapping):
            delta_base = base_value if isinstance(base_value, Mapping) else {}
            reconciled[key] = apply_cache_delta(delta_base, pending_value, latest_value)
        else:
            reconciled[key] = copy.deepcopy(pending_value)
    return reconciled


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
        self._legacy_marker_path = self.cache_path.with_name(
            f"{self.cache_path.name}.legacy-migrated"
        )
        self._lock_path = self.cache_path.with_name(f"{self.cache_path.name}.lock")
        self._warn = warn or (lambda _message: None)

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """Serialize cache mutations across CLI/MCP subprocesses."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def load(self) -> dict[str, Any]:
        """Return normalized cache data, or defaults when the file is unusable."""
        if not self.cache_path.exists():
            return default_cache_payload()
        payload = self._read_object(self.cache_path)
        return _normalize_payload(payload)

    def reload(self, current: Mapping[str, Any]) -> dict[str, Any]:
        """Reload valid disk data without discarding the current state on read failure."""
        if not self.cache_path.exists():
            return copy.deepcopy(dict(current))
        payload = self._read_object(self.cache_path)
        if payload is None:
            return copy.deepcopy(dict(current))
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
        try:
            with self._exclusive_lock():
                return self._save_unlocked(payload)
        except OSError as exc:
            self._warn(f"Could not lock CLI cache {self.cache_path}: {exc}")
            return False

    def _save_unlocked(self, payload: Mapping[str, Any]) -> bool:
        """Persist while the caller owns the cache mutation lock."""
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
        except (OSError, RecursionError, TypeError, ValueError) as exc:
            self._warn(f"Could not save CLI cache {self.cache_path}: {exc}")
            return False
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def transaction(
        self,
        current: Mapping[str, Any],
        mutate: MutationCallback,
    ) -> tuple[dict[str, Any], bool]:
        """Apply one read-modify-write operation under an inter-process lock."""
        try:
            with self._exclusive_lock():
                if self.cache_path.exists():
                    payload = self._read_object(self.cache_path)
                    latest = (
                        _normalize_payload(payload)
                        if payload is not None
                        else copy.deepcopy(dict(current))
                    )
                else:
                    latest = default_cache_payload()
                try:
                    working = copy.deepcopy(latest)
                except RecursionError as exc:
                    self._warn(f"Could not copy CLI cache {self.cache_path}: {exc}")
                    return latest, False
                try:
                    changed = bool(mutate(working))
                except RecursionError as exc:
                    self._warn(f"Could not mutate CLI cache {self.cache_path}: {exc}")
                    return latest, False
                if not changed:
                    return latest, False
                if not self._save_unlocked(working):
                    return latest, False
                return _normalize_payload(working), True
        except OSError as exc:
            self._warn(f"Could not lock CLI cache {self.cache_path}: {exc}")
            return copy.deepcopy(dict(current)), False

    def clear(self) -> bool:
        """Remove the canonical cache file if present."""
        try:
            with self._exclusive_lock():
                self.cache_path.unlink(missing_ok=True)
            return True
        except OSError as exc:
            self._warn(f"Could not clear CLI cache {self.cache_path}: {exc}")
            return False

    def migrate_legacy(self) -> bool:
        """Merge a legacy temp cache without overwriting canonical conflicts."""
        legacy_path = self.legacy_path
        if (
            legacy_path is None
            or legacy_path == self.cache_path
            or not legacy_path.exists()
        ):
            return False

        try:
            with self._exclusive_lock():
                if not legacy_path.exists() or self._legacy_marker_path.exists():
                    return False
                legacy = self._read_object(legacy_path)
                if legacy is None:
                    return False
                canonical: dict[str, Any] = {}
                if self.cache_path.exists():
                    canonical = self._read_object(self.cache_path) or {}
                merged = merge_cache_payloads(legacy, canonical)
                if not self._save_unlocked(_normalize_payload(merged)):
                    return False
                return self._mark_legacy_migrated()
        except OSError as exc:
            self._warn(f"Could not lock CLI cache migration {self.cache_path}: {exc}")
            return False

    def _mark_legacy_migrated(self) -> bool:
        try:
            self._legacy_marker_path.parent.mkdir(parents=True, exist_ok=True)
            with self._legacy_marker_path.open("x", encoding="utf-8") as handle:
                handle.write("migrated\n")
                handle.flush()
                os.fsync(handle.fileno())
            return True
        except FileExistsError:
            return True
        except OSError as exc:
            self._warn(f"Could not mark legacy CLI cache as migrated: {exc}")
            return False
