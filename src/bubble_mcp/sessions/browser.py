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
    captured_write_headers: dict[str, str] = {}
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

        def remember_write_headers(request: Any) -> None:
            try:
                if "bubble.io/appeditor/write" not in str(request.url):
                    return
                raw_headers = request.headers
            except Exception:
                return
            for key, value in raw_headers.items():
                lowered = str(key).lower()
                if lowered.startswith("x-bubble-") or lowered in {"x-requested-with", "user-agent"}:
                    captured_write_headers[lowered] = str(value)

        context.on("request", remember_write_headers)
        page.goto(target_url, wait_until="domcontentloaded")

        deadline = time.monotonic() + max(1, wait_seconds)
        while time.monotonic() < deadline:
            try:
                cookie_string = _bubble_cookie_header(context)
                if cookie_string:
                    last_cookie_string = cookie_string
                last_user_agent = _first_open_page_user_agent(context, last_user_agent)
            except Exception:
                break
            time.sleep(1)

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

    if not last_cookie_string:
        raise RuntimeError("No bubble.io cookies were captured. Log in before the wait timeout expires.")

    return session_from_payload(
        {
            "appId": app_id,
            "url": target_url,
            "headers": {
                "Cookie": last_cookie_string,
                "User-Agent": last_user_agent,
                **captured_write_headers,
            },
            "source": "browser",
        }
    )
