from bubble_mcp.sessions.store import (
    VolatileSessionStore,
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
