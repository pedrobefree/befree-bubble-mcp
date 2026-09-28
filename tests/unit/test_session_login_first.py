"""Session login opens Bubble's login page first and detects login by cookie, not by URL.

No browser: a fake Playwright records where the page was sent and serves cookies that change
as the fake user "logs in".
"""

from __future__ import annotations

import sys
import types
from typing import Any, Self

import pytest

from bubble_mcp.sessions import browser
from bubble_mcp.sessions.browser import (
    LOGIN_URL,
    BrowserSessionPollResult,
    capture_session_with_playwright,
    editor_url_for,
    logged_in_user,
)


class _Page:
    def __init__(self, context: _Context) -> None:
        self.context = context
        self.visits: list[str] = []
        self.url = "about:blank"

    def goto(self, url: str, **kwargs: Any) -> None:
        self.visits.append(url)
        self.context.on_goto(url)
        # An expired login loads the editor, then gets sent to the home page.
        self.url = "https://bubble.io/" if "page?id=" in url and self.context.expired else url

    def evaluate(self, script: str) -> Any:
        return "kaimia-app" if "page?id=kaimia-app" in self.url else None

    def is_closed(self) -> bool:
        return False


class _Context:
    def __init__(self, *, logged_in: bool = False, logs_in_after: int | None = None, expired: bool = False) -> None:
        self.logged_in = logged_in
        # A stale login: the cookie is there, the editor sends the page away.
        self.expired = expired
        self.cleared = False
        # How many cookie reads after the login page opens before the user id appears.
        self.logs_in_after = logs_in_after
        self.on_login_page = False
        self.reads = 0
        self.page = _Page(self)
        self.pages = [self.page]
        self.closed = False

    def on_goto(self, url: str) -> None:
        self.on_login_page = url == LOGIN_URL

    def cookies(self, url: str | None = None) -> list[dict[str, str]]:
        if self.on_login_page and self.logs_in_after is not None:
            self.reads += 1
            if self.reads > self.logs_in_after:
                self.logged_in = True
        value = "%22user-1%22" if self.logged_in else ""
        return [{"name": "ajs_user_id", "value": value}, {"name": "b", "value": "session"}]

    def clear_cookies(self, **kwargs: Any) -> None:
        self.cleared = True
        self.logged_in = False
        self.expired = False

    def on(self, event: str, handler: Any) -> None:
        pass

    def new_page(self) -> _Page:
        return self.page

    def close(self) -> None:
        self.closed = True


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch, context: _Context) -> None:
    class _Chromium:
        def launch_persistent_context(self, *args: Any, **kwargs: Any) -> _Context:
            return context

    class _Playwright:
        chromium = _Chromium()

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: _Playwright()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        browser,
        "_poll_browser_session",
        lambda *args, **kwargs: BrowserSessionPollResult("b=session", "ua", True, "validated"),
    )
    monkeypatch.setattr(browser, "_require_complete_capture", lambda **kwargs: None)


def test_the_editor_url_names_the_branch_and_omits_main() -> None:
    assert editor_url_for("kaimia-app", "93k8b") == (
        "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=93k8b"
    )
    assert editor_url_for("kaimia-app", "test") == "https://bubble.io/page?id=kaimia-app&tab=Design&name=index"


@pytest.mark.parametrize("value", ["", '""', "%22%22", "null"])
def test_an_empty_user_id_cookie_is_not_a_login(value: str) -> None:
    class Context:
        def cookies(self, url: str | None = None) -> list[dict[str, str]]:
            return [{"name": "ajs_user_id", "value": value}]

    assert logged_in_user(Context()) is None


def test_a_logged_out_profile_goes_to_the_login_page_then_the_branch_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    context = _Context(logs_in_after=3)
    _install_fake_playwright(monkeypatch, context)
    messages: list[str] = []

    session = capture_session_with_playwright(
        app_id="kaimia-app",
        app_version="93k8b",
        user_data_dir=tmp_path,
        wait_seconds=60,
        progress=messages.append,
    )

    assert context.page.visits == [
        LOGIN_URL,
        "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=93k8b",
    ]
    assert any("login detected" in message.lower() for message in messages)
    assert session.app_version == "93k8b"


def test_a_logged_in_profile_goes_straight_to_the_editor(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    context = _Context(logged_in=True)
    _install_fake_playwright(monkeypatch, context)

    capture_session_with_playwright(app_id="kaimia-app", app_version="93k8b", user_data_dir=tmp_path, wait_seconds=60)

    assert context.page.visits == ["https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=93k8b"]


def test_login_first_false_opens_the_editor_directly(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    context = _Context()
    _install_fake_playwright(monkeypatch, context)

    capture_session_with_playwright(
        app_id="kaimia-app", user_data_dir=tmp_path, wait_seconds=60, login_first=False
    )

    assert context.page.visits == ["https://bubble.io/page?id=kaimia-app&tab=Design&name=index"]


def test_no_login_before_the_deadline_fails_and_closes_the_browser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    context = _Context()  # never logs in
    _install_fake_playwright(monkeypatch, context)
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(browser.time, "monotonic", lambda: float(next(clock)))

    with pytest.raises(RuntimeError, match="ajs_user_id"):
        capture_session_with_playwright(app_id="kaimia-app", user_data_dir=tmp_path, wait_seconds=60)

    assert context.page.visits == [LOGIN_URL]
    assert context.closed is True


def test_the_login_tool_passes_login_first_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.server.schemas import list_tool_schemas
    from bubble_mcp.server.tools import call_tool

    schema = {tool["name"]: tool for tool in list_tool_schemas()}["bubble_session_login"]
    assert schema["inputSchema"]["properties"]["login_first"]["default"] is True

    seen: dict[str, Any] = {}

    def fake_capture(**kwargs: Any) -> Any:
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr("bubble_mcp.server.tools.capture_session_with_playwright", fake_capture)

    with pytest.raises(RuntimeError, match="stop here"):
        call_tool("bubble_session_login", {"profile": "p", "app_id": "a", "login_first": False})
    assert seen["login_first"] is False


def test_an_expired_login_that_kept_its_cookie_is_sent_to_the_login_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    context = _Context(logged_in=True, expired=True, logs_in_after=2)
    _install_fake_playwright(monkeypatch, context)
    messages: list[str] = []

    capture_session_with_playwright(
        app_id="kaimia-app", app_version="93k8b", user_data_dir=tmp_path, wait_seconds=60, progress=messages.append
    )

    editor = "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=93k8b"
    assert context.page.visits == [editor, LOGIN_URL, editor]
    assert context.cleared is True
    assert any("expired" in message for message in messages)
    assert not any("Already logged in" in message for message in messages)
