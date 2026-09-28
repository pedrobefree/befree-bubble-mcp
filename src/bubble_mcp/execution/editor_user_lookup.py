"""Find a Bubble user's unique id by email through the editor, without a Data API token.

bubble_run_as needs a user id, and resolving one from an email used to require the app's Data
API token; on the team server there was none, so the agent drove the editor's Data tab with its
own Playwright script. This does the same, through the stored editor session.

The Data tab's search request is not reproducible by hand - its body is an encrypted "z" blob -
but its RESPONSE is plain JSON: each hit carries ``_id`` and, for users,
``authentication.email.email`` (captured on mcp-test-app, 2026-09-28). So the lookup opens the
tab on the User type, reads the search answers the page receives, and when the first page does
not hold the email, types it into the tab's own search box and reads the next answer.

It reads the development database, which branches share. Live data is a separate database the
tab only shows after "Switch to live database"; that is not done here.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from typing import Any

DATA_TAB_URL = (
    "https://bubble.io/page?id={app_id}&tab=Data&name=index&version={app_version}"
    "&subtab=App+Data&type_id=user"
)
SEARCH_BOX_PLACEHOLDER = "Search for data entries"
SEARCH_RESPONSE_MARKER = "/elasticsearch/search"
FIRST_PAGE_WAIT_SEC = 15.0
FILTERED_WAIT_SEC = 15.0


def user_ids_by_email(payloads: Iterable[Any]) -> dict[str, str]:
    """Every user hit in the given search answers, as lowercased email -> unique id."""

    found: dict[str, str] = {}
    for payload in payloads:
        hits = ((payload or {}).get("hits") or {}).get("hits") if isinstance(payload, dict) else None
        for hit in hits or []:
            source = hit.get("_source") if isinstance(hit, dict) else None
            if not isinstance(source, dict) or source.get("_type", hit.get("_type")) != "user":
                continue
            email = ((source.get("authentication") or {}).get("email") or {}).get("email") or source.get("email")
            user_id = source.get("_id") or hit.get("_id")
            if isinstance(email, str) and isinstance(user_id, str):
                found[email.strip().lower()] = user_id
    return found


def find_user_id_in_editor(
    profile: str,
    app_id: str,
    email: str,
    *,
    app_version: str = "test",
    headless: bool = True,
    timeout_sec: int = 120,
    open_page: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Return ``{"ok": True, "user_id": ...}`` for ``email``, read from the editor's Data tab."""

    if app_version == "live":
        return {
            "ok": False,
            "error": "live_lookup_unsupported",
            "message": (
                "Looking a user up through the editor reads the development database; live users "
                "live in a separate one. Pass user_id, or configure a Data API token for live."
            ),
        }
    wanted = email.strip().lower()
    if open_page is None:
        from bubble_mcp.execution.live_node_read import APPQUERY_READY_SCRIPT, _open_editor_page

        def open_page(**kwargs: Any) -> Any:
            return _open_editor_page(**kwargs)

        ready_script: str | None = APPQUERY_READY_SCRIPT
    else:
        ready_script = None

    answers: list[Any] = []

    def remember(response: Any) -> None:
        try:
            if SEARCH_RESPONSE_MARKER in str(response.url):
                answers.append(json.loads(response.text()))
        except Exception:
            pass

    def wait_for_match(seconds: float) -> str | None:
        deadline = monotonic() + seconds
        while True:
            match = user_ids_by_email(answers).get(wanted)
            if match or monotonic() >= deadline:
                return match
            sleep(0.5)

    url = DATA_TAB_URL.format(app_id=app_id, app_version=app_version)
    try:
        with open_page(
            profile=profile, app_id=app_id, app_version=app_version, headless=headless, timeout_sec=timeout_sec, url=url
        ) as page:
            page.on("response", remember)
            page.reload(wait_until="domcontentloaded")
            if ready_script:
                page.wait_for_function(ready_script, timeout=timeout_sec * 1000)
            user_id = wait_for_match(FIRST_PAGE_WAIT_SEC)
            searched = False
            if not user_id:
                searched = True
                box = page.get_by_placeholder(SEARCH_BOX_PLACEHOLDER)
                box.fill(email.strip())
                box.press("Enter")
                user_id = wait_for_match(FILTERED_WAIT_SEC)
    except Exception as error:  # noqa: BLE001 - reported, the caller decides
        return {
            "ok": False,
            "error": "editor_lookup_failed",
            "message": f"Could not read users from the editor's Data tab: {type(error).__name__}: {error}",
        }
    if not user_id:
        return {
            "ok": False,
            "error": "user_not_found",
            "message": (
                f"No user with email '{email}' in the development database of '{app_id}' "
                f"({'after searching for it' if searched else 'on the first page'})."
            ),
        }
    return {"ok": True, "user_id": user_id, "email": email, "source": "editor_data_tab"}
