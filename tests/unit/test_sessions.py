import pytest

from bubble_mcp.sessions.browser import (
    _poll_browser_session,
    _require_complete_capture,
    capture_session_with_playwright,
)
from bubble_mcp.sessions.store import (
    VolatileSessionStore,
    editor_write_session_status,
    list_sessions,
    load_session,
    save_session,
    session_from_payload,
)


def test_session_store_keeps_metadata_and_redacts_debug_snapshot() -> None:
    store = VolatileSessionStore()

    store.set_session("synthetic-app", {"cookie": "session=secret-value"}, source="manual")

    assert store.get_metadata("synthetic-app")["source"] == "manual"  # type: ignore[index]
    snapshot = store.safe_debug_snapshot()
    assert snapshot["synthetic-app"]["headers"]["cookie"] == "[REDACTED]"  # type: ignore[index]


def test_session_import_persists_restricted_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    session = session_from_payload(
        {
            "appId": "synthetic-app",
            "url": "https://bubble.io/page?name=synthetic-app",
            "headers": {"Cookie": "sid=secret", "User-Agent": "test"},
            "appVersion": "test",
        }
    )

    path = save_session("dev", session, tmp_path)

    assert path.exists()
    assert load_session("dev", tmp_path).cookies == "sid=secret"  # type: ignore[union-attr]
    assert list_sessions(tmp_path)[0]["profile"] == "dev"


def test_browser_session_poll_keeps_cookies_when_interrupted() -> None:
    class FakePage:
        def is_closed(self) -> bool:
            return False

        def evaluate(self, _script: str) -> str:
            return "FakeBrowser/1.0"

    class FakeContext:
        pages = [FakePage()]

        def cookies(self, _url: str | None = None) -> list[dict[str, str]]:
            return [{"name": "sid", "value": "captured"}]

    def interrupted_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    progress_events: list[str] = []
    result = _poll_browser_session(
        FakeContext(),
        wait_seconds=180,
        sleep=interrupted_sleep,
        monotonic=lambda: 0,
        progress=progress_events.append,
    )

    assert result.cookie_string == "sid=captured"
    assert result.user_agent == "FakeBrowser/1.0"
    assert result.stop_reason == "interrupted"
    assert result.validated is False
    assert progress_events == [
        "Session cookies detected. You can close the browser now; the CLI will save the newest captured session."
    ]


def test_browser_session_poll_waits_for_validated_editor_session_before_close_guidance() -> None:
    class FakePage:
        def is_closed(self) -> bool:
            return False

        def evaluate(self, _script: str) -> str:
            return "FakeBrowser/1.0"

    class FakeContext:
        pages = [FakePage()]

        def cookies(self, _url: str | None = None) -> list[dict[str, str]]:
            return [{"name": "sid", "value": "captured"}]

    ticks = {"count": 0}

    def fake_sleep(_seconds: float) -> None:
        ticks["count"] += 1

    def fake_monotonic() -> float:
        return float(ticks["count"])

    progress_events: list[str] = []
    result = _poll_browser_session(
        FakeContext(),
        wait_seconds=5,
        sleep=fake_sleep,
        monotonic=fake_monotonic,
        progress=progress_events.append,
        editor_session_ready=lambda _cookie_string: ticks["count"] >= 2,
    )

    assert result.cookie_string == "sid=captured"
    assert result.user_agent == "FakeBrowser/1.0"
    assert result.stop_reason == "validated"
    assert result.validated is True
    assert progress_events == [
        "Session cookies detected. Waiting for a validated editor session "
        "(anonymous/login-page cookies are not accepted) -- keep the Bubble editor open.",
        "Bubble editor session validated (calculate_derived succeeded). You can close the browser now.",
    ]


def test_browser_session_poll_validates_once_more_at_timeout_boundary() -> None:
    class FakePage:
        def is_closed(self) -> bool:
            return False

        def evaluate(self, _script: str) -> str:
            return "FakeBrowser/1.0"

    class FakeContext:
        pages = [FakePage()]

        def cookies(self, _url: str | None = None) -> list[dict[str, str]]:
            return [{"name": "sid", "value": "captured"}]

    ticks = {"count": 0}

    def fake_sleep(_seconds: float) -> None:
        ticks["count"] += 1

    result = _poll_browser_session(
        FakeContext(),
        wait_seconds=1,
        sleep=fake_sleep,
        monotonic=lambda: float(ticks["count"]),
        editor_session_ready=lambda _cookie_string: ticks["count"] == 1,
    )

    assert result.validated is True
    assert result.stop_reason == "validated"


def test_browser_session_poll_stops_when_browser_is_closed_or_cancelled() -> None:
    class ClosedContext:
        pages: list[object] = []

    closed = _poll_browser_session(ClosedContext(), wait_seconds=600)
    cancelled = _poll_browser_session(ClosedContext(), wait_seconds=600, cancelled=lambda: True)

    assert closed.stop_reason == "browser_closed"
    assert cancelled.stop_reason == "cancelled"


@pytest.mark.parametrize("wait_seconds", [0, -5])
def test_browser_session_capture_rejects_non_positive_wait(wait_seconds: int) -> None:
    with pytest.raises(ValueError, match="wait_seconds must be at least 1"):
        capture_session_with_playwright(app_id="synthetic-app", wait_seconds=wait_seconds)


@pytest.mark.parametrize(
    ("cookie_string", "write_headers", "expected"),
    [
        ("", {}, "No bubble.io cookies were captured within 600 seconds"),
        ("sid=captured", {}, "timed out after 600 seconds while waiting for Bubble editor request headers"),
        (
            "sid=captured",
            {"x-bubble-client-version": "test"},
            "timed out after 600 seconds while waiting for the authenticated Bubble editor session",
        ),
    ],
)
def test_capture_timeout_diagnostics_cover_partial_two_factor_state(
    cookie_string: str,
    write_headers: dict[str, str],
    expected: str,
) -> None:
    with pytest.raises(RuntimeError, match=expected):
        _require_complete_capture(
            cookie_string=cookie_string,
            write_headers=write_headers,
            validated=False,
            stop_reason="timeout",
            wait_seconds=600,
        )


def test_editor_write_session_status_requires_cookies_and_editor_headers() -> None:
    session = session_from_payload(
        {
            "appId": "synthetic-app",
            "headers": {"cookie": "sid=secret", "x-bubble-client-version": "client-version"},
        }
    )

    assert editor_write_session_status(session)["write_ready"] is True
    cookies_only = session_from_payload({"appId": "synthetic-app", "headers": {"cookie": "sid=secret"}})
    assert editor_write_session_status(cookies_only)["missing"] == ["editor_request_headers"]
