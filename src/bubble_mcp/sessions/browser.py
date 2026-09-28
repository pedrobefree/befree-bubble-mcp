"""Browser-assisted Bubble session capture."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from bubble_mcp.execution.client import BubbleEditorClient, default_http_transport
from bubble_mcp.sessions.constants import DEFAULT_LOGIN_WAIT_SECONDS, MIN_LOGIN_WAIT_SECONDS
from bubble_mcp.sessions.store import BubbleSessionData, session_from_payload

ProgressCallback = Callable[[str], None]
CancellationCheck = Callable[[], bool]
EDITOR_VALIDATION_INTERVAL_SEC = 2.0
EDITOR_VALIDATION_TIMEOUT_SEC = 10.0
# Login is user-driven and the browser is closed the moment this budget runs out, so it has to
# cover the slowest realistic human path: password, then a two-factor code that arrives by email
# or SMS and may need a retry. The old 120-180s budgets expired mid-2FA and killed the window
# before the user could finish. Waiting longer costs nothing on the happy path -- the poll loop
# exits as soon as the editor session validates.


# Bubble's own login screen. Opening the editor for someone who is not logged in does not show it,
# so on a server without a terminal nobody can sign in from there (team server, 2026-09-25).
LOGIN_URL = "https://bubble.io/login?mode=login"
# After signing in on LOGIN_URL, Bubble stays on that URL, so the URL cannot tell that login
# happened. This cookie, holding the user id, can: it is empty or absent until then.
LOGGED_IN_COOKIE = "ajs_user_id"
_EMPTY_COOKIE_VALUES = {"", '""', "%22%22", "null", "%22null%22", "undefined"}


def editor_url_for(app_id: str, app_version: str | None = None) -> str:
    """The editor URL for ``app_id`` opened on ``app_version`` (main when not given)."""

    url = f"https://bubble.io/page?id={app_id}&tab=Design&name=index"
    version = str(app_version or "").strip()
    if version and version != "test":
        url += f"&version={version}"
    return url


def logged_in_user(context: Any) -> str | None:
    """The Bubble user id the browser is logged in as, or None when it is not logged in."""

    for url in ("https://bubble.io", None):
        try:
            cookies = context.cookies(url) if url else context.cookies()
        except Exception:
            continue
        for cookie in cookies:
            if cookie.get("name") != LOGGED_IN_COOKIE:
                continue
            value = str(cookie.get("value") or "").strip()
            if value not in _EMPTY_COOKIE_VALUES:
                return value
    return None


def _wait_for_login(
    context: Any,
    *,
    deadline: float,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    cancelled: CancellationCheck | None = None,
) -> str:
    """Wait for the login cookie; return why the wait ended."""

    while True:
        if cancelled is not None and cancelled():
            return "cancelled"
        if not _has_open_page(context):
            return "browser_closed"
        if logged_in_user(context):
            return "logged_in"
        remaining = deadline - monotonic()
        if remaining <= 0:
            return "timeout"
        sleep(min(1, remaining))


def _ensure_logged_in(
    context: Any,
    page: Any,
    *,
    wait_seconds: int,
    deadline: float,
    progress: ProgressCallback | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    cancelled: CancellationCheck | None = None,
) -> None:
    """Open Bubble's login page and wait for a login, unless the profile is logged in already."""

    if logged_in_user(context):
        if progress is not None:
            progress("Already logged in to Bubble in this browser profile.")
        return
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    if progress is not None:
        progress(f"Opened {LOGIN_URL}. Log in to Bubble; the editor opens once login is detected.")
    reason = _wait_for_login(context, deadline=deadline, sleep=sleep, monotonic=monotonic, cancelled=cancelled)
    if reason == "logged_in":
        if progress is not None:
            progress("Bubble login detected.")
        return
    if reason == "cancelled":
        raise SessionCaptureCancelled("Bubble session login was cancelled by the MCP client.")
    if reason == "browser_closed":
        raise RuntimeError("The login browser was closed before Bubble login was detected.")
    raise RuntimeError(
        f"No Bubble login within {wait_seconds} seconds (the {LOGGED_IN_COOKIE} cookie stayed empty). "
        "If a two-factor code was still pending, rerun with a larger wait_seconds (CLI: --wait-seconds)."
    )


class SessionCaptureCancelled(RuntimeError):
    """Raised when an MCP client cancels an interactive login capture."""


@dataclass(frozen=True)
class BrowserSessionPollResult:
    cookie_string: str
    user_agent: str
    validated: bool
    stop_reason: str


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


def _has_open_page(context: Any) -> bool:
    for page in getattr(context, "pages", []):
        try:
            if not page.is_closed():
                return True
        except Exception:
            continue
    return False


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
    cancelled: CancellationCheck | None = None,
) -> BrowserSessionPollResult:
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

    validated = False
    reported_cookies = bool(last_cookie_string)
    reported_write_ready = False
    deadline = monotonic() + wait_seconds
    stop_reason = "timeout"
    while True:
        if cancelled is not None and cancelled():
            stop_reason = "cancelled"
            break
        if not _has_open_page(context):
            stop_reason = "browser_closed"
            break
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
                stop_reason = "validated"
                break
            last_user_agent = _first_open_page_user_agent(context, last_user_agent)
        except KeyboardInterrupt:
            stop_reason = "interrupted"
            break
        except Exception:
            stop_reason = "browser_error"
            break
        remaining = deadline - monotonic()
        if remaining <= 0:
            stop_reason = "timeout"
            break
        try:
            sleep(min(1, remaining))
        except KeyboardInterrupt:
            stop_reason = "interrupted"
            break
    return BrowserSessionPollResult(
        cookie_string=last_cookie_string,
        user_agent=last_user_agent,
        validated=validated,
        stop_reason=stop_reason,
    )


def _require_complete_capture(
    *,
    cookie_string: str,
    write_headers: dict[str, str],
    validated: bool,
    stop_reason: str,
    wait_seconds: int,
) -> None:
    if not cookie_string:
        if stop_reason == "timeout":
            raise RuntimeError(
                f"No bubble.io cookies were captured within {wait_seconds} seconds. If a two-factor code "
                "was still pending, rerun with a larger wait_seconds (CLI: --wait-seconds)."
            )
        raise RuntimeError(
            "No bubble.io cookies were captured before the login browser closed or capture stopped. "
            "Run login again and keep the browser open until the editor session is validated."
        )
    if not (
        write_headers.get("x-bubble-client-version")
        or write_headers.get("x-bubble-client-commit-timestamp")
    ):
        if stop_reason == "timeout":
            raise RuntimeError(
                f"Session capture timed out after {wait_seconds} seconds while waiting for Bubble editor "
                "request headers. If login or two-factor authentication was still in progress, rerun with "
                "a larger wait_seconds (CLI: --wait-seconds)."
            )
        raise RuntimeError(
            "Bubble cookies were captured, but editor request headers were not. "
            "Open the Bubble editor for the target app, wait until it fully loads, and rerun session login."
        )
    if not validated:
        if stop_reason == "timeout":
            raise RuntimeError(
                f"Session capture timed out after {wait_seconds} seconds while waiting for the authenticated "
                "Bubble editor session to pass calculate_derived. If a two-factor code was still pending, "
                "rerun with a larger wait_seconds (CLI: --wait-seconds)."
            )
        raise RuntimeError(
            "Bubble cookies and editor headers were captured, but the session never passed a real "
            "calculate_derived check -- it is likely an anonymous or login-page session, not an "
            "authenticated editor session. Log in with an account that has EDITOR access to this app, "
            "wait for the editor to fully load, and rerun session login."
        )


def capture_session_with_playwright(
    *,
    app_id: str,
    editor_url: str | None = None,
    headless: bool = False,
    wait_seconds: int = DEFAULT_LOGIN_WAIT_SECONDS,
    user_data_dir: Path | None = None,
    app_version: str | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCheck | None = None,
    login_first: bool = True,
) -> BubbleSessionData:
    """Open a local browser and capture Bubble cookies.

    With ``login_first`` (the default) a browser profile that is not logged in is sent to
    Bubble's login page first, and the editor is opened once the login cookie appears; the
    editor itself never shows a login screen to someone signed out. ``wait_seconds`` covers the
    login and the editor validation together.

    Playwright is an optional dependency. Install with
    `pip install "befree-bubble-mcp[browser]"` and run `playwright install`.
    """

    wait_seconds = int(wait_seconds)
    if wait_seconds < MIN_LOGIN_WAIT_SECONDS:
        raise ValueError(f"wait_seconds must be at least {MIN_LOGIN_WAIT_SECONDS}.")
    if cancelled is not None and cancelled():
        raise SessionCaptureCancelled("Bubble session login was cancelled by the MCP client.")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for browser session capture. "
            'Install with: python -m pip install "befree-bubble-mcp[browser]" '
            "&& python -m playwright install chromium"
        ) from exc

    target_url = editor_url or editor_url_for(app_id, app_version)
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
        progress(f"Waiting up to {wait_seconds} seconds for a validated editor session.")
    with sync_playwright() as playwright:
        try:
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
        except Exception as exc:  # playwright.Error lacks a stable import path here
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                import sys as _sys

                raise RuntimeError(
                    "Playwright browser binaries are missing for THIS MCP server's environment. "
                    "Install them with the MCP's own Python: "
                    f"'{_sys.executable}' -m playwright install chromium "
                    "(a global 'playwright install' uses a different Playwright version and does not help)."
                ) from exc
            raise
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
        deadline = time.monotonic() + wait_seconds
        if login_first:
            try:
                _ensure_logged_in(
                    context, page, wait_seconds=wait_seconds, deadline=deadline, progress=progress, cancelled=cancelled
                )
            except BaseException:
                _close_quietly(context, browser)
                raise
        page.goto(target_url, wait_until="domcontentloaded")
        if progress is not None:
            progress(
                "Browser opened on the editor. Keep the editor tab open until capture is confirmed."
                if login_first
                else "Browser opened. Log in to Bubble and keep the editor tab open until capture is confirmed."
            )

        poll_result = _poll_browser_session(
            context,
            wait_seconds=max(MIN_LOGIN_WAIT_SECONDS, int(deadline - time.monotonic())),
            last_cookie_string=last_cookie_string,
            last_user_agent=last_user_agent,
            progress=progress,
            editor_session_ready=editor_session_ready,
            cancelled=cancelled,
        )
        last_cookie_string = poll_result.cookie_string
        last_user_agent = poll_result.user_agent
        validated = poll_result.validated

        try:
            cookie_string = _bubble_cookie_header(context)
            if cookie_string:
                last_cookie_string = cookie_string
        except Exception:
            pass
        _close_quietly(context, browser)
        if poll_result.stop_reason == "cancelled":
            raise SessionCaptureCancelled("Bubble session login was cancelled by the MCP client.")
        if poll_result.stop_reason == "interrupted" and not last_cookie_string:
            raise RuntimeError(
                "Session capture was interrupted before bubble.io cookies were captured. "
                "Run login again and wait until the CLI prints the saved session JSON."
            )

    _require_complete_capture(
        cookie_string=last_cookie_string,
        write_headers=captured_write_headers,
        validated=validated,
        stop_reason=poll_result.stop_reason,
        wait_seconds=wait_seconds,
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


def _close_quietly(context: Any, browser: Any) -> None:
    try:
        context.close()
    except Exception:
        pass
    if browser is not None:
        try:
            browser.close()
        except Exception:
            pass
