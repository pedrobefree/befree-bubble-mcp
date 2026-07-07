from bubble_mcp.sessions.store import (
    VolatileSessionStore,
    editor_write_session_status,
    list_sessions,
    load_session,
    save_session,
    session_from_payload,
)
from bubble_mcp.sessions.browser import _poll_browser_session


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
    cookie_string, user_agent, interrupted = _poll_browser_session(
        FakeContext(),
        wait_seconds=180,
        sleep=interrupted_sleep,
        monotonic=lambda: 0,
        progress=progress_events.append,
    )

    assert cookie_string == "sid=captured"
    assert user_agent == "FakeBrowser/1.0"
    assert interrupted is True
    assert progress_events == [
        "Session cookies detected. You can close the browser now; the CLI will save the newest captured session."
    ]


def test_browser_session_poll_waits_for_editor_headers_before_close_guidance() -> None:
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
    cookie_string, user_agent, interrupted = _poll_browser_session(
        FakeContext(),
        wait_seconds=5,
        sleep=fake_sleep,
        monotonic=fake_monotonic,
        progress=progress_events.append,
        editor_headers_ready=lambda: ticks["count"] >= 2,
    )

    assert cookie_string == "sid=captured"
    assert user_agent == "FakeBrowser/1.0"
    assert interrupted is False
    assert progress_events == [
        "Session cookies detected. Keep the Bubble editor open until editor request headers are detected.",
        "Bubble editor request headers detected. The session is write-ready; you can close the browser now.",
    ]


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
