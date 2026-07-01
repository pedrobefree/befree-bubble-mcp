"""Browser-assisted Bubble session capture."""

from __future__ import annotations

from typing import Any

from bubble_mcp.sessions.store import BubbleSessionData, session_from_payload


def capture_session_with_playwright(
    *,
    app_id: str,
    editor_url: str | None = None,
    headless: bool = False,
    wait_seconds: int = 120,
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
            'Install with: pip install "befree-bubble-mcp[browser]" && playwright install chromium'
        ) from exc

    target_url = editor_url or f"https://bubble.io/page?id={app_id}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(max(1, wait_seconds) * 1000)
        cookies: list[dict[str, Any]] = context.cookies("https://bubble.io")
        user_agent = page.evaluate("() => navigator.userAgent")
        browser.close()

    cookie_string = "; ".join(
        f"{cookie.get('name')}={cookie.get('value')}"
        for cookie in cookies
        if cookie.get("name") and cookie.get("value")
    )
    if not cookie_string:
        raise RuntimeError("No bubble.io cookies were captured. Log in before the wait timeout expires.")

    return session_from_payload(
        {
            "appId": app_id,
            "url": target_url,
            "headers": {
                "Cookie": cookie_string,
                "User-Agent": str(user_agent or "befree-bubble-mcp"),
            },
            "source": "browser",
        }
    )
