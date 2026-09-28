"""Session login goes through Bubble's login page and detects login by asking for the app.

No browser: a fake Playwright records where the page was sent and answers the in-page access
check with 200 once the fake user has "logged in" and 401 before.

The login cookie (ajs_user_id) is deliberately not the signal: Bubble's analytics keep the user
id in localStorage and write the cookie back on every page load, so an expired login keeps it
(kaimia-app, 2026-09-28).
"""

from __future__ import annotations

import sys
import types
from typing import Any, Self

import pytest

from bubble_mcp.sessions import browser
from bubble_mcp.sessions.browser import (
    APP_ACCESS_SCRIPT,
    LOGIN_URL,
    BrowserSessionPollResult,
    capture_session_with_playwright,
    editor_url_for,
    has_app_access,
)

EDITOR = "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=93k8b"


class _Page:
    def __init__(self, context: _Context) -> None:
        self.context = context
        self.visits: list[str] = []
        self.url = "about:blank"

    def goto(self, url: str, **kwargs: Any) -> None:
        self.visits.append(url)
        self.url = url

    def evaluate(self, script: str, arg: Any = None) -> Any:
        assert script == APP_ACCESS_SCRIPT
        return self.context.access_status()

    def is_closed(self) -> bool:
        return False


class _Context:
    def __init__(self, *, logged_in: bool = False, logs_in_after: int | None = None) -> None:
        self.logged_in = logged_in
        # How many access checks on the login page before the fake user finishes logging in.
        self.logs_in_after = logs_in_after
        self.checks = 0
        self.page = _Page(self)
        self.pages = [self.page]
        self.closed = False

    def access_status(self) -> int:
        if self.page.url == LOGIN_URL and self.logs_in_after is not None:
            self.checks += 1
            if self.checks > self.logs_in_after:
                self.logged_in = True
        return 200 if self.logged_in else 401

    def cookies(self, url: str | None = None) -> list[dict[str, str]]:
        # An expired login keeps this cookie: it must not count as a login.
        return [{"name": "ajs_user_id", "value": "%22user-1%22"}, {"name": "b", "value": "session"}]

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
    clock = [0.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr(browser.time, "sleep", sleep)
    monkeypatch.setattr(browser.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        browser,
        "_poll_browser_session",
        lambda *args, **kwargs: BrowserSessionPollResult("b=session", "ua", True, "validated"),
    )
    monkeypatch.setattr(browser, "_require_complete_capture", lambda **kwargs: None)


def test_the_editor_url_names_the_branch_and_omits_main() -> None:
    assert editor_url_for("kaimia-app", "93k8b") == EDITOR
    assert editor_url_for("kaimia-app", "test") == "https://bubble.io/page?id=kaimia-app&tab=Design&name=index"


@pytest.mark.parametrize(("status", "expected"), [(200, True), (401, False), (403, False), (0, None), (500, None)])
def test_the_access_check_reads_the_status(status: int, expected: bool | None) -> None:
    class Page:
        def evaluate(self, script: str, arg: Any = None) -> int:
            return status

    assert has_app_access(Page(), "kaimia-app") is expected


def test_a_logged_out_profile_waits_on_the_login_page_then_opens_the_branch_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    context = _Context(logs_in_after=3)
    _install_fake_playwright(monkeypatch, context)
    messages: list[str] = []

    session = capture_session_with_playwright(
        app_id="kaimia-app", app_version="93k8b", user_data_dir=tmp_path, wait_seconds=60, progress=messages.append
    )

    assert context.page.visits == [LOGIN_URL, EDITOR]
    assert any("login detected" in message.lower() for message in messages)
    assert session.app_version == "93k8b"


def test_a_stale_login_cookie_does_not_skip_the_login_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    context = _Context(logs_in_after=2)  # cookie present from the start, access only after login
    _install_fake_playwright(monkeypatch, context)
    messages: list[str] = []

    capture_session_with_playwright(
        app_id="kaimia-app", app_version="93k8b", user_data_dir=tmp_path, wait_seconds=60, progress=messages.append
    )

    assert context.checks > 2
    assert not any("Already logged in" in message for message in messages)


def test_a_logged_in_profile_goes_on_to_the_editor_at_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    context = _Context(logged_in=True)
    _install_fake_playwright(monkeypatch, context)
    messages: list[str] = []

    capture_session_with_playwright(
        app_id="kaimia-app", app_version="93k8b", user_data_dir=tmp_path, wait_seconds=60, progress=messages.append
    )

    assert context.page.visits == [LOGIN_URL, EDITOR]
    assert any("Already logged in" in message for message in messages)


def test_login_first_false_opens_the_editor_directly(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    context = _Context()
    _install_fake_playwright(monkeypatch, context)

    capture_session_with_playwright(app_id="kaimia-app", user_data_dir=tmp_path, wait_seconds=60, login_first=False)

    assert context.page.visits == ["https://bubble.io/page?id=kaimia-app&tab=Design&name=index"]


def test_no_login_before_the_deadline_fails_and_closes_the_browser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    context = _Context()  # never logs in
    _install_fake_playwright(monkeypatch, context)

    with pytest.raises(RuntimeError, match="No Bubble login with access to 'kaimia-app'"):
        capture_session_with_playwright(app_id="kaimia-app", user_data_dir=tmp_path, wait_seconds=60)

    assert context.page.visits == [LOGIN_URL]
    assert context.closed is True


def test_an_editor_that_leaves_the_app_while_validating_sends_back_to_the_login_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    context = _Context(logged_in=True)
    _install_fake_playwright(monkeypatch, context)
    reasons = iter(["editor_left", "validated"])
    polls: list[bool] = []

    def poll(*args: Any, editor_left: Any = None, **kwargs: Any) -> BrowserSessionPollResult:
        polls.append(editor_left is not None)
        return BrowserSessionPollResult("b=session", "ua", True, next(reasons))

    monkeypatch.setattr(browser, "_poll_browser_session", poll)

    capture_session_with_playwright(app_id="kaimia-app", app_version="93k8b", user_data_dir=tmp_path, wait_seconds=120)

    assert context.page.visits == [LOGIN_URL, EDITOR, LOGIN_URL, EDITOR]
    assert polls == [True, True]


def test_an_editor_that_leaves_the_app_twice_is_an_error_naming_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    context = _Context(logged_in=True)
    _install_fake_playwright(monkeypatch, context)
    monkeypatch.setattr(
        browser,
        "_poll_browser_session",
        lambda *args, **kwargs: BrowserSessionPollResult("b=session", "ua", False, "editor_left"),
    )

    with pytest.raises(RuntimeError, match="no editor access"):
        capture_session_with_playwright(app_id="kaimia-app", user_data_dir=tmp_path, wait_seconds=120)
    assert context.closed is True


def test_the_poll_stops_as_soon_as_the_editor_leaves_the_app() -> None:
    class Page:
        def is_closed(self) -> bool:
            return False

    class Context:
        pages = [Page()]

        def cookies(self, url: str | None = None) -> list[dict[str, str]]:
            return []

    result = browser._poll_browser_session(
        Context(), wait_seconds=600, sleep=lambda seconds: None, editor_left=lambda: True
    )

    assert result.stop_reason == "editor_left"


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
