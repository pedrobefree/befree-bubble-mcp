"""Registry snapshot and diff support."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.language.registry import build_language_index, current_language_entries


def _safe_version(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)


def _snapshot_dir() -> Path:
    return get_config_dir() / "language" / "registry-snapshots"


def _snapshot_path(version: str) -> Path:
    return _snapshot_dir() / f"{_safe_version(version)}.json"


def current_language_snapshot(*, profile: str | None = None) -> dict[str, Any]:
    index = build_language_index(profile=profile)
    return {
        "registry_version": index["registry_version"],
        "generated_at": index["generated_at"],
        "entries": [
            {
                "name": entry["name"],
                "schema_hash": entry["schema_hash"],
                "family": entry["family"],
                "source": entry["source"],
                "risk": entry["risk"],
            }
            for entry in current_language_entries()
        ],
    }


def save_language_snapshot(snapshot: dict[str, Any] | None = None, *, profile: str | None = None) -> dict[str, Any]:
    payload = snapshot or current_language_snapshot(profile=profile)
    version = str(payload.get("registry_version") or "")
    if not version:
        raise ValueError("language snapshot requires registry_version.")
    _snapshot_dir().mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(version)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "registry_version": version, "path": str(path)}


def _load_snapshot(version: str) -> dict[str, Any]:
    path = _snapshot_path(version)
    if not path.exists():
        raise ValueError(f"Unknown language registry snapshot: {version}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected language registry snapshot object in {path}")
    return payload


def _entry_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = snapshot.get("entries")
    if not isinstance(entries, list):
        return {}
    return {
        str(entry.get("name") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("name") or "")
    }


def language_diff(*, since: str, current: str | None = None, profile: str | None = None) -> dict[str, Any]:
    current_snapshot = current_language_snapshot(profile=profile) if current is None else _load_snapshot(current)
    if current is None:
        save_language_snapshot(current_snapshot, profile=profile)
    old_snapshot = _load_snapshot(since)
    old_entries = _entry_map(old_snapshot)
    new_entries = _entry_map(current_snapshot)
    added = sorted(name for name in new_entries if name not in old_entries)
    removed = sorted(name for name in old_entries if name not in new_entries)
    changed = sorted(
        name
        for name in new_entries.keys() & old_entries.keys()
        if new_entries[name].get("schema_hash") != old_entries[name].get("schema_hash")
        or new_entries[name].get("family") != old_entries[name].get("family")
        or new_entries[name].get("risk") != old_entries[name].get("risk")
    )
    return {
        "ok": True,
        "since": str(old_snapshot.get("registry_version") or since),
        "current": str(current_snapshot.get("registry_version") or current),
        "added": added,
        "changed": changed,
        "removed": removed,
        "counts": {"added": len(added), "changed": len(changed), "removed": len(removed)},
    }
