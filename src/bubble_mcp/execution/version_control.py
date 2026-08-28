"""Bubble version control over HTTP: create a savepoint, list them, restore one.

Captured from real editor traffic on 2026-08-27 (docs/capture-version-control-*.json). None of
these need a browser - the stored session is enough, which is what makes taking a savepoint before
a session's first write affordable.

A savepoint is NOT a branch. `commit_test_version` is a plain POST with a message; the heavyweight
`create_new_app_version` in `editor_api.py` is a different thing.

RESTORE IS WHOLE-APP TIME TRAVEL
--------------------------------
`restore_to` takes an epoch-ms instant - the same value the path API returns at
``["last_change_date"]`` - and reverts the ENTIRE app version to it, including work done after that
instant that the caller wanted to keep. It is not "undo this edit". That is why executing one
requires `confirm=true` on top of `execute=true`, the same bar `bubble_branch_delete` sets.
"""

from __future__ import annotations

from typing import Any

from bubble_mcp.execution.editor_api import (
    BubbleEditorApiClient,
    _client,
    _editor_session_id,
    _load_session_for_profile,
    _resolve_app_id,
    _resolve_app_version,
)


def create_savepoint(
    *,
    profile: str,
    message: str,
    app_id: str | None = None,
    app_version: str | None = None,
    session_id: str | None = None,
    execute: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    """Create a Bubble savepoint on `app_version`, returning the editor's response."""

    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    version = _resolve_app_version(profile, session, app_version)
    text = str(message or "").strip()
    if not text:
        # The restore history is a list of messages; an unlabelled entry cannot be found again.
        raise ValueError("create_savepoint requires a message describing what is being saved.")
    payload = {
        "appname": appname,
        "app_version": version,
        "message": text,
        "session_id": _editor_session_id(session_id),
    }
    result = _client(client).post(
        "/appeditor/commit_test_version", payload, session, dry_run=not execute
    )
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "app_version": version,
        "message": text,
        "executed": execute,
        **result,
    }


def list_restore_history(
    *,
    profile: str,
    app_id: str | None = None,
    app_version: str | None = None,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    """List the savepoints `app_version` can be restored to. Read-only."""

    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    version = _resolve_app_version(profile, session, app_version)
    payload = {"appname": appname, "app_version": version}
    result = _client(client).post("/appeditor/get_restore_history", payload, session)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "app_version": version,
        **result,
    }


def restore_to_timestamp(
    *,
    profile: str,
    timestamp: int,
    app_id: str | None = None,
    app_version: str | None = None,
    execute: bool = False,
    confirm: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    """Revert the whole app version to `timestamp` (epoch ms). See the module docstring."""

    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    version = _resolve_app_version(profile, session, app_version)
    try:
        instant = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("restore_to_timestamp requires an epoch-ms timestamp.") from None
    if instant <= 0:
        raise ValueError(
            f"restore_to_timestamp requires a positive epoch-ms timestamp; got {timestamp!r}."
        )
    if execute and not confirm:
        raise ValueError(
            "restore_to_timestamp requires confirm=true when execute=true: it reverts the entire "
            f"'{version}' version to that instant, discarding every change made after it."
        )
    payload = {"appname": appname, "app_version": version, "timestamp": instant}
    result = _client(client).post("/appeditor/restore_to", payload, session, dry_run=not execute)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "app_version": version,
        "timestamp": instant,
        "executed": execute,
        **result,
    }
