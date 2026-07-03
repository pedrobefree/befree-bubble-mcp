"""Browser-assisted Bubble session capture."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from bubble_mcp.sessions.store import BubbleSessionData, session_from_payload

ProgressCallback = Callable[[str], None]


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
) -> tuple[str, str, bool]:
    """Poll a Playwright context and keep the newest usable Bubble session state.

    The login flow is intentionally user-driven. Closing the browser window or
    interrupting the command after login should not discard a valid session that
    was already observed during the wait loop.
    """

    interrupted = False
    reported_cookies = bool(last_cookie_string)
    deadline = monotonic() + max(1, wait_seconds)
    while monotonic() < deadline:
        try:
            cookie_string = _bubble_cookie_header(context)
            if cookie_string:
                last_cookie_string = cookie_string
                if not reported_cookies:
                    reported_cookies = True
                    if progress is not None:
                        progress(
                            "Session cookies detected. You can close the browser now; "
                            "the CLI will save the newest captured session."
                        )
            last_user_agent = _first_open_page_user_agent(context, last_user_agent)
            sleep(1)
        except KeyboardInterrupt:
            interrupted = True
            break
        except Exception:
            break
    return last_cookie_string, last_user_agent, interrupted


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
                    "accept-language",
                    "cache-control",
                    "origin",
                    "priority",
                    "sec-ch-ua",
                    "sec-ch-ua-mobile",
                    "sec-ch-ua-platform",
                    "sec-fetch-dest",
                    "sec-fetch-mode",
                    "sec-fetch-site",
                    "x-requested-with",
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

        last_cookie_string, last_user_agent, interrupted = _poll_browser_session(
            context,
            wait_seconds=wait_seconds,
            last_cookie_string=last_cookie_string,
            last_user_agent=last_user_agent,
            progress=progress,
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
