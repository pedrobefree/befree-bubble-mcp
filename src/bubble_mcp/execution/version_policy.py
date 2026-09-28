"""Where this MCP may write in an app: a branch always, main only when the app has no branch.

Main (``test``) was made read-only after an agent's unreviewed write landed on the team's shared
main (2026-09-25). But an app on a plan without branches has only ``test`` and ``live``, and a
blanket rule left it with nowhere to write at all. So the rule follows the app:

- the app has at least one branch: main is read-only; work goes to a branch - an existing one,
  or a new one made with ``bubble_branch_create`` - and reaches main through a reviewed merge;
- the app has no branch: ``test`` is where development happens, and writing there is allowed;
- ``live`` is never written.

The answer comes from ``/appeditor/get_versions`` (the call ``bubble_branch_list`` makes), cached
per app for a few minutes and dropped when a branch is created or deleted. When the versions
cannot be read, main stays read-only: not knowing is not permission.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from bubble_mcp.sessions.store import BubbleSessionData

MAIN_EDITABLE = "test"
LIVE = "live"
BRANCH_CACHE_SEC = 300.0
SHOWN_BRANCHES = 5
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

Fetch = Callable[[BubbleSessionData, str], dict[str, Any]]


def _fetch_versions(session: BubbleSessionData, app_id: str) -> dict[str, Any]:
    from bubble_mcp.execution.editor_api import BubbleEditorApiClient

    return BubbleEditorApiClient().post("/appeditor/get_versions", {"appname": app_id}, session)


def app_branches(
    session: BubbleSessionData | None,
    app_id: str,
    *,
    fetch: Fetch | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    use_cache: bool = True,
) -> dict[str, Any]:
    """``{"ok": True, "branches": [...]}`` - every version id that is neither test nor live."""

    app = str(app_id or "").strip()
    if session is None or not app:
        return {"ok": False, "branches": [], "error": "no_session", "message": "No stored editor session to ask with."}
    now = monotonic()
    cached = _CACHE.get(app)
    if use_cache and cached is not None and now - cached[0] < BRANCH_CACHE_SEC:
        return cached[1]
    try:
        result = (fetch or _fetch_versions)(session, app)
    except Exception as error:  # noqa: BLE001 - reported; main then stays read-only
        return {"ok": False, "branches": [], "error": "versions_unreadable", "message": f"{type(error).__name__}: {error}"}
    versions = result.get("response") if isinstance(result, dict) else None
    if not (isinstance(result, dict) and result.get("ok") and isinstance(versions, dict)):
        return {
            "ok": False,
            "branches": [],
            "error": "versions_unreadable",
            "message": f"Bubble did not list the app's versions (status {result.get('status') if isinstance(result, dict) else None}).",
        }
    # Deleted branches stay in the list with deleted=true, and Bubble's copies of live
    # ("live.<change>") are readonly; neither is somewhere to develop (kaimia-app, 2026-09-28).
    branches = sorted(
        str(key)
        for key, entry in versions.items()
        if str(key) not in (MAIN_EDITABLE, LIVE)
        and not (isinstance(entry, dict) and (entry.get("deleted") or entry.get("readonly")))
    )
    answer = {
        "ok": True,
        "branches": branches,
        "names": {key: str((versions.get(key) or {}).get("display") or key) for key in branches},
    }
    _CACHE[app] = (now, answer)
    return answer


def forget(app_id: str | None = None) -> None:
    """Drop cached version lists - after a branch is created or deleted, or for every app."""

    for key in [key for key in _CACHE if app_id is None or key == app_id]:
        _CACHE.pop(key, None)


def write_policy(session: BubbleSessionData | None, app_id: str, **kwargs: Any) -> dict[str, Any]:
    """What an agent needs before writing: the branches, whether main takes writes, and why."""

    listed = app_branches(session, app_id, **kwargs)
    if not listed.get("ok"):
        return {
            "branches": [],
            "main_writable": False,
            "live_writable": False,
            "advice": (
                "The app's versions could not be read, so main (test) stays read-only for now "
                f"({listed.get('message') or listed.get('error')}). Write to a branch id, or check "
                "the session with bubble_session_check."
            ),
        }
    branches = listed["branches"]
    if not branches:
        return {
            "branches": [],
            "main_writable": True,
            "live_writable": False,
            "advice": (
                "This app has no branches, only test and live, so development happens on test: "
                "writes with app_version='test' are allowed (after the session's automatic "
                "savepoint). live is never written."
            ),
        }
    shown = ", ".join(f"{key} ({listed['names'].get(key, key)})" for key in branches[:SHOWN_BRANCHES])
    if len(branches) > SHOWN_BRANCHES:
        shown += f", and {len(branches) - SHOWN_BRANCHES} more"
    return {
        "branches": branches,
        "main_writable": False,
        "live_writable": False,
        "advice": (
            f"This app has branches ({shown}), so main (test) is read-only: write to a branch and "
            "merge it through a reviewed branch merge. For new work, create a development branch "
            "with bubble_branch_create (from_app_version='test'), or pass an existing branch id as "
            "app_version."
        ),
    }


def main_write_allowed(version: str | None, session: BubbleSessionData | None, app_id: str) -> tuple[bool, str]:
    """(allowed, advice) for a write aimed at ``version`` when that version is main."""

    target = str(version or MAIN_EDITABLE).strip().lower()
    if target == LIVE:
        return False, "live is the deployed app and is never written by this MCP; deploy from test instead."
    policy = write_policy(session, app_id)
    return bool(policy["main_writable"]), str(policy["advice"])
