from bubble_mcp.sessions.store import (
    VolatileSessionStore,
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
