"""Context freshness and runtime loading helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.context.mutation_overlay import apply_mutation_overlay
from bubble_mcp.context.source import load_context


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def context_freshness(
    context: BubbleProjectContext,
    *,
    path: Path | None = None,
    max_age_hours: int = 24,
) -> dict[str, Any]:
    metadata = context.metadata
    generated = (
        _parse_datetime(metadata.get("saved_at"))
        or _parse_datetime(metadata.get("captured_at"))
        or _parse_datetime(metadata.get("generated_at"))
    )
    source = "metadata"
    if generated is None and path is not None and path.exists():
        generated = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        source = "file_mtime"
    if generated is None:
        return {
            "status": "unknown",
            "source": context.source,
            "last_updated_at": None,
            "age_seconds": None,
            "max_age_hours": max_age_hours,
            "stale": True,
        }
    age_seconds = max(0, int((datetime.now(timezone.utc) - generated).total_seconds()))
    stale = age_seconds > max_age_hours * 3600
    return {
        "status": "stale" if stale else "fresh",
        "source": context.source,
        "timestamp_source": source,
        "last_updated_at": generated.isoformat(),
        "age_seconds": age_seconds,
        "max_age_hours": max_age_hours,
        "stale": stale,
    }


def load_context_with_overlay(
    path: Path,
    *,
    profile: str | None = None,
    app_id: str | None = None,
) -> BubbleProjectContext:
    context = load_context(path)
    if profile:
        context = apply_mutation_overlay(context, profile=profile, app_id=app_id or context.app_id)
    return context
