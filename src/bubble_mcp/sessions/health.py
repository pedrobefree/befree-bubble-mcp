"""Is the stored editor session still logged in? One HTTP call, no browser.

An expired session does not fail loudly where agents look: a live read spends a browser launch
before it reports not_logged_in, and an agent that does not recognise the error retries, tries
other tools, and only later concludes it was logged out. On a metered API with a weaker model
that is a loop of paid calls that could never have worked. This answers up front, in ~0.3s,
with the same probe session login trusts: ``/appeditor/calculate_derived`` answers 200 with
fingerprints for a live session and 401 for an expired one (measured 2026-09-28 on mcp-test-app,
kaimia-app and auto-on).

A logged-in answer is cached for a few minutes per stored session, so gating every call on it
costs one request per window. A logged-out answer is never cached: the next call after a new
login must see it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from bubble_mcp.execution.client import BubbleEditorClient, default_http_transport
from bubble_mcp.sessions.store import BubbleSessionData, editor_write_session_status, load_session

CHECK_TIMEOUT_SEC = 10.0
LOGGED_IN_CACHE_SEC = 300.0
_CACHE: dict[tuple[str, str], float] = {}

Probe = Callable[[BubbleSessionData], dict[str, Any]]


def _probe(session: BubbleSessionData) -> dict[str, Any]:
    client = BubbleEditorClient(transport=default_http_transport, timeout=CHECK_TIMEOUT_SEC)
    return client.calculate_derived({}, session, dry_run=False)


def login_next_action(profile: str) -> str:
    return (
        f"Stop and ask the user to log in: run bubble_session_login with profile '{profile}' "
        f"(CLI: bubble-mcp session login --profile {profile} --app-id <app>). Every call that "
        "needs the Bubble editor fails until then, so do not retry or try other tools first."
    )


def check_session(
    profile: str,
    *,
    probe: Probe | None = None,
    use_cache: bool = True,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Report whether ``profile``'s stored session is logged in to the Bubble editor."""

    session = load_session(profile)
    if session is None:
        return _answer(profile, False, "no_session", "No Bubble session is stored for this profile.")
    status = editor_write_session_status(session)
    if not status["write_ready"]:
        return _answer(
            profile,
            False,
            "incomplete_session",
            f"The stored session is missing {', '.join(status['missing'])}; it was not captured "
            "from a loaded editor.",
            session=session,
        )

    key = (profile, str(session.captured_at or ""))
    now = monotonic()
    checked = _CACHE.get(key)
    if use_cache and checked is not None and now - checked < LOGGED_IN_CACHE_SEC:
        return _answer(profile, True, "logged_in", "", session=session, cached=True)

    try:
        result = (probe or _probe)(session)
    except Exception as error:  # noqa: BLE001 - an HTML answer or a network failure, reported
        text = str(error)
        if "expired" in text.lower() or "html" in text.lower():
            return _answer(profile, False, "expired", text, session=session)
        return _answer(profile, None, "check_failed", f"{type(error).__name__}: {text}", session=session)

    if result.get("ok"):
        _CACHE[key] = now
        return _answer(profile, True, "logged_in", "", session=session)
    _CACHE.pop(key, None)
    if result.get("reason") == "auth_blocked" or result.get("status") in (401, 403):
        return _answer(
            profile,
            False,
            "expired",
            f"Bubble answered {result.get('status')} to the stored session: it has expired or was "
            "logged out.",
            session=session,
        )
    return _answer(
        profile,
        None,
        "check_failed",
        f"Bubble answered status {result.get('status')} without the expected shape; login state unknown.",
        session=session,
    )


def forget(profile: str | None = None) -> None:
    """Drop cached answers - for one profile, or all."""

    for key in [key for key in _CACHE if profile is None or key[0] == profile]:
        _CACHE.pop(key, None)


def _answer(
    profile: str,
    logged_in: bool | None,
    reason: str,
    message: str,
    *,
    session: BubbleSessionData | None = None,
    cached: bool = False,
) -> dict[str, Any]:
    answer: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "logged_in": logged_in,
        "reason": reason,
        "cached": cached,
    }
    if session is not None:
        answer["app_id"] = session.app_id
        answer["captured_at"] = session.captured_at
    if message:
        answer["message"] = message
    if logged_in is False:
        answer["next_action"] = login_next_action(profile)
    return answer
