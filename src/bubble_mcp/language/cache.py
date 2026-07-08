"""Incremental cache for framework-scoped Bubble MCP language indexes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir


_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _safe(value: str) -> str:
    segment = str(value or "").strip()
    if not _SAFE_SEGMENT_RE.fullmatch(segment) or segment in {".", ".."}:
        raise ValueError("Language cache keys must be safe path segments.")
    return segment


def _cache_path(framework: str, profile: str) -> Path:
    return get_config_dir() / "language" / "cache" / _safe(framework) / f"{_safe(profile)}.json"


def cache_language_index(framework: str, profile: str, index: dict[str, Any]) -> dict[str, Any]:
    """Persist a framework/profile language index for incremental reuse."""

    path = _cache_path(framework, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temporary_path.replace(path)
    return {
        "ok": True,
        "path": str(path),
        "registry_version": str(index.get("registry_version") or ""),
    }


def cached_language_index(framework: str, profile: str) -> dict[str, Any]:
    """Load a cached framework/profile language index when available."""

    path = _cache_path(framework, profile)
    if not path.exists():
        return {"ok": False, "error": "language_cache_miss", "path": str(path)}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "language_cache_invalid", "path": str(path)}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "language_cache_invalid", "path": str(path)}
    return {"ok": True, "path": str(path), "index": payload}
