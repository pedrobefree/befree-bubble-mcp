"""One Bubble savepoint per working session, taken before that session's first write.

Granularity is deliberate. `commit_test_version` is cheap enough to call before every edit, but
every call lands in Bubble's restore history: a forty-write session would leave forty entries to
scroll past when looking for the point worth returning to. One labelled entry per session is what
a human can actually use.

Undoing a single edit is a different problem with a different answer - `restore_to` reverts the
whole version, so per-edit rollback needs the before-state of the paths that edit touched, not a
savepoint.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from bubble_mcp.compiler.payload import bubble_session_id
from bubble_mcp.core.config import get_config_dir


DEFAULT_IDLE_SECONDS = 1800

# One id for the life of this MCP process, which is what "a working session" means here.
# `bubble_session_id()` mints a fresh timestamp-based id on every call, so calling it per write
# would make every write look like a new session and take its own savepoint - the exact flooding
# this module exists to avoid.
_PROCESS_SESSION_ID = bubble_session_id()


def process_session_id() -> str:
    """The session identity the savepoint marker is keyed by. Stable for this process."""

    return _PROCESS_SESSION_ID


def _safe_name(value: str) -> str:
    text = str(value or "").strip()
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text) or "default"


def session_savepoint_path(profile: str, app_id: str) -> Path:
    return get_config_dir() / "savepoints" / f"{_safe_name(profile)}-{_safe_name(app_id)}.json"


def _serialize(marker: dict[str, Any]) -> str:
    return json.dumps(marker, indent=2, sort_keys=True) + "\n"


def _read_marker(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable marker means "take a new savepoint"
        return {}
    return parsed if isinstance(parsed, dict) else {}


def ensure_session_savepoint(
    *,
    profile: str,
    app_id: str,
    app_version: str,
    session_id: str,
    message: str,
    create: Callable[..., dict[str, Any]],
    now: float | None = None,
    idle_seconds: int = DEFAULT_IDLE_SECONDS,
) -> dict[str, Any]:
    """Create a savepoint if this session does not have a live one yet.

    Returns a report, never raises: the savepoint protects the write that follows, and failing to
    take one is a reason to warn, not a reason to refuse the work. A savepoint that failed leaves
    no marker behind, so the next write tries again instead of silently running unprotected.
    """

    moment = time.time() if now is None else float(now)
    path = session_savepoint_path(profile, app_id)
    marker = _read_marker(path)
    # The idle window measures silence, not age: a long stretch of steady work is one session,
    # so every write that reuses the savepoint pushes `last_activity` forward.
    last_activity = float(marker.get("last_activity") or marker.get("created_at") or 0)
    if (
        marker.get("session_id") == session_id
        and marker.get("app_version") == app_version
        and moment - last_activity <= idle_seconds
    ):
        marker["last_activity"] = moment
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_serialize(marker), encoding="utf-8")
        return {"created": False, "reason": "session_savepoint_exists", "savepoint": marker}

    try:
        result = create(message=message)
    except Exception as exc:  # noqa: BLE001 - see the docstring: never block the write
        return {"created": False, "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(result, dict) or not result.get("ok"):
        return {"created": False, "error": "savepoint_not_created", "result": result}

    saved = {
        "profile": profile,
        "app_id": app_id,
        "app_version": app_version,
        "session_id": session_id,
        "message": message,
        "created_at": moment,
        "last_activity": moment,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize(saved), encoding="utf-8")
    return {"created": True, "savepoint": saved, "result": result}
