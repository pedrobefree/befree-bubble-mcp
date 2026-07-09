"""Browser-assisted Bubble session capture."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from bubble_mcp.execution.client import BubbleEditorClient, default_http_transport
from bubble_mcp.sessions.store import BubbleSessionData, session_from_payload

ProgressCallback = Callable[[str], None]
EDITOR_VALIDATION_INTERVAL_SEC = 2.0
EDITOR_VALIDATION_TIMEOUT_SEC = 10.0


def _cookie_header(cookies: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{cookie.get('name')}={cookie.get('value')}"
        for cookie in cookies
        if cookie.get("name") and cookie.get("value")
    )


def _bubble_cookie_header(context: Any) -> str:
    cookies: list[dict[str, Any]] = []
    try:
        cookies.extend(context.cookies())
    except Exception:
        pass
    for url in ("https://bubble.io", "https://login.bubble.io", "https://app.bubble.io"):
        try:
            cookies.extend(context.cookies(url))
        except Exception:
            continue
    by_name: dict[str, dict[str, Any]] = {}
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        if name:
            by_name[name] = cookie
    return _cookie_header(list(by_name.values()))


def _first_open_page_user_agent(context: Any, fallback: str) -> str:
    for open_page in getattr(context, "pages", []):
        try:
            if not open_page.is_closed():
                return str(open_page.evaluate("() => navigator.userAgent") or fallback)
        except Exception:
            continue
    return fallback


def _poll_browser_session(
    context: Any,
    *,
    wait_seconds: int,
    last_cookie_string: str = "",
    last_user_agent: str = "befree-bubble-mcp",
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    progress: ProgressCallback | None = None,
    editor_session_ready: Callable[[str], bool] | None = None,
) -> tuple[str, str, bool, bool]:
    """Poll a Playwright context and keep the newest usable Bubble session state.

    The login flow is intentionally user-driven. Closing the browser window or
    interrupting the command after login should not discard a valid session that
    was already observed during the wait loop.

    `editor_session_ready`, when given, must perform a real authenticated
    request (not just check for header presence) because Bubble sends
    x-bubble-client-* headers on anonymous/login pages too -- treating their
    mere presence as "logged in" closes the browser before the user finishes
    authenticating and leaves a session that then fails with 401 on every
    editor call.
    """

    interrupted = False
    validated = False
    reported_cookies = bool(last_cookie_string)
    reported_write_ready = False
    deadline = monotonic() + max(1, wait_seconds)
    while monotonic() < deadline:
        try:
            cookie_string = _bubble_cookie_header(context)
            if cookie_string:
                last_cookie_string = cookie_string
                if not reported_cookies:
                    reported_cookies = True
                    if progress is not None:
                        if editor_session_ready is None:
                            progress(
                                "Session cookies detected. You can close the browser now; "
                                "the CLI will save the newest captured session."
                            )
                        else:
                            progress(
                                "Session cookies detected. Waiting for a validated editor session "
                                "(anonymous/login-page cookies are not accepted) -- keep the Bubble "
                                "editor open."
                            )
            if (
                editor_session_ready is not None
                and last_cookie_string
                and not reported_write_ready
                and editor_session_ready(last_cookie_string)
            ):
                reported_write_ready = True
                validated = True
                if progress is not None:
                    progress(
                        "Bubble editor session validated (calculate_derived succeeded). "
                        "You can close the browser now."
                    )
                break
            last_user_agent = _first_open_page_user_agent(context, last_user_agent)
            sleep(1)
        except KeyboardInterrupt:
            interrupted = True
            break
        except Exception:
            break
    return last_cookie_string, last_user_agent, interrupted, validated


def capture_session_with_playwright(
    *,
    app_id: str,
    editor_url: str | None = None,
    headless: bool = False,
    wait_seconds: int = 120,
    user_data_dir: Path | None = None,
    app_version: str | None = None,
    progress: ProgressCallback | None = None,
) -> BubbleSessionData:
    """Open a local browser and capture Bubble cookies.

    Playwright is an optional dependency. Install with
    `pip install "befree-bubble-mcp[browser]"` and run `playwright install`.
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for browser session capture. "
            'Install with: python -m pip install "befree-bubble-mcp[browser]" '
            "&& python -m playwright install chromium"
        ) from exc

    target_url = editor_url or f"https://bubble.io/page?id={app_id}"
    last_cookie_string = ""
    last_user_agent = "befree-bubble-mcp"
    captured_write_headers: dict[str, str] = {}
    reported_write_headers = False
    editor_client = BubbleEditorClient(transport=default_http_transport, timeout=EDITOR_VALIDATION_TIMEOUT_SEC)
    last_validation_check = 0.0

    def editor_session_ready(cookie_string: str) -> bool:
        nonlocal last_validation_check
        if not captured_write_headers:
            return False
        now = time.monotonic()
        if now - last_validation_check < EDITOR_VALIDATION_INTERVAL_SEC:
            return False
        last_validation_check = now
        probe_session = BubbleSessionData(
            app_id=app_id,
            url=target_url,
            method="POST",
            headers={**captured_write_headers, "cookie": cookie_string},
            cookies=cookie_string,
            app_version=app_version or "test",
            captured_at="",
            source="browser",
        )
        try:
            result = editor_client.calculate_derived({}, probe_session, dry_run=False)
        except Exception:
            return False
        return bool(result.get("ok"))

    if progress is not None:
        progress(f"Opening Bubble editor login browser for app '{app_id}'.")
        progress(f"Waiting up to {max(1, wait_seconds)} seconds for session cookies.")
    with sync_playwright() as playwright:
        if user_data_dir is not None:
            user_data_dir.mkdir(parents=True, exist_ok=True)
            context = playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
            )
            browser = None
        else:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        def remember_bubble_headers(request: Any) -> None:
            nonlocal reported_write_headers
            try:
                if "bubble.io/" not in str(request.url):
                    return
                raw_headers = request.headers
            except Exception:
                return
            for key, value in raw_headers.items():
                lowered = str(key).lower()
                if lowered.startswith("x-bubble-") or lowered in {
                    "accept",
                    "accept-language",
                    "authorization",
                    "cache-control",
                    "origin",
                    "priority",
                    "referer",
                    "sec-ch-ua",
                    "sec-ch-ua-mobile",
                    "sec-ch-ua-platform",
                    "sec-fetch-dest",
                    "sec-fetch-mode",
                    "sec-fetch-site",
                    "x-csrf-token",
                    "x-requested-with",
                    "x-xsrf-token",
                    "user-agent",
                }:
                    captured_write_headers[lowered] = str(value)
            if captured_write_headers and not reported_write_headers:
                reported_write_headers = True
                if progress is not None:
                    progress("Bubble editor request headers detected.")

        context.on("request", remember_bubble_headers)
        page.goto(target_url, wait_until="domcontentloaded")
        if progress is not None:
            progress("Browser opened. Log in to Bubble and keep the editor tab open until capture is confirmed.")

        last_cookie_string, last_user_agent, interrupted, validated = _poll_browser_session(
            context,
            wait_seconds=wait_seconds,
            last_cookie_string=last_cookie_string,
            last_user_agent=last_user_agent,
            progress=progress,
            editor_session_ready=editor_session_ready,
        )

        try:
            cookie_string = _bubble_cookie_header(context)
            if cookie_string:
                last_cookie_string = cookie_string
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if interrupted and not last_cookie_string:
            raise RuntimeError(
                "Session capture was interrupted before bubble.io cookies were captured. "
                "Run login again and wait until the CLI prints the saved session JSON."
            )

    if not last_cookie_string:
        raise RuntimeError("No bubble.io cookies were captured. Log in before the wait timeout expires.")
    if not (
        captured_write_headers.get("x-bubble-client-version")
        or captured_write_headers.get("x-bubble-client-commit-timestamp")
    ):
        raise RuntimeError(
            "Bubble cookies were captured, but editor request headers were not. "
            "Open the Bubble editor for the target app, wait until it fully loads, and rerun session login."
        )
    if not validated:
        raise RuntimeError(
            "Bubble cookies and editor headers were captured, but the session never passed a real "
            "calculate_derived check -- it is likely an anonymous or login-page session, not an "
            "authenticated editor session. Log in with an account that has EDITOR access to this app, "
            "wait for the editor to fully load, and rerun session login."
        )

    if progress is not None:
        header_count = len(captured_write_headers)
        progress(f"Session capture complete: cookies saved, {header_count} Bubble header(s) captured.")

    return session_from_payload(
        {
            "appId": app_id,
            "url": target_url,
            "headers": {
                "Cookie": last_cookie_string,
                "User-Agent": last_user_agent,
                **captured_write_headers,
            },
            "appVersion": app_version or "test",
            "source": "browser",
        }
    )
