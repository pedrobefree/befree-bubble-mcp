"""Persist successful editor mutations as a local discovery overlay."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bubble_mcp.context.detector import context_cache_dir


def _safe_name(value: str) -> str:
    text = str(value or "").strip()
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text) or "default"


def mutation_overlay_path(profile: str, app_id: str) -> Path:
    return context_cache_dir() / _safe_name(profile) / f"{_safe_name(app_id)}-mutation-overlay.json"


def record_mutation_overlay(
    *,
    profile: str,
    app_id: str,
    payload: dict[str, Any],
    source: str,
    response: Any | None = None,
) -> Path | None:
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        return None

    path = mutation_overlay_path(profile, app_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = parsed
        except Exception:
            existing = {}

    entries = existing.get("entries")
    if not isinstance(entries, list):
        entries = []

    entries.append(
        {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile,
            "app_id": app_id,
            "source": source,
            "response": response if isinstance(response, dict) else None,
            "changes": json.loads(json.dumps(changes)),
        }
    )
    existing.update(
        {
            "version": 1,
            "profile": profile,
            "app_id": app_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
        }
    )
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
