"""Browser-assisted Bubble session capture."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from bubble_mcp.sessions.store import BubbleSessionData, session_from_payload


def _cookie_header(cookies: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{cookie.get('name')}={cookie.get('value')}"
        for cookie in cookies
        if cookie.get("name") and cookie.get("value")
    )


def capture_session_with_playwright(
    *,
    app_id: str,
    editor_url: str | None = None,
    headless: bool = False,
    wait_seconds: int = 120,
    user_data_dir: Path | None = None,
) -> BubbleSessionData:
    """Open a local browser and capture Bubble cookies.

    Playwright is an optional dependency. Install with
    `pip install "befree-bubble-mcp[browser]"` and run `playwright install`.
    """

    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for browser session capture. "
            'Install with: python -m pip install "befree-bubble-mcp[browser]" '
            "&& python -m playwright install chromium"
        ) from exc

    target_url = editor_url or f"https://bubble.io/page?id={app_id}"
    last_cookie_string = ""
    last_user_agent = "befree-bubble-mcp"
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
        page.goto(target_url, wait_until="domcontentloaded")

        deadline = time.monotonic() + max(1, wait_seconds)
        while time.monotonic() < deadline:
            try:
                cookie_string = _cookie_header(context.cookies("https://bubble.io"))
                if cookie_string:
                    last_cookie_string = cookie_string
                last_user_agent = str(page.evaluate("() => navigator.userAgent") or last_user_agent)
                page.wait_for_timeout(1000)
            except Exception:
                break

        try:
            cookie_string = _cookie_header(context.cookies("https://bubble.io"))
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

    if not last_cookie_string:
        raise RuntimeError("No bubble.io cookies were captured. Log in before the wait timeout expires.")

    return session_from_payload(
        {
            "appId": app_id,
            "url": target_url,
            "headers": {
                "Cookie": last_cookie_string,
                "User-Agent": last_user_agent,
            },
            "source": "browser",
        }
    )
