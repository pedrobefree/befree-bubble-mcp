from bubble_mcp.sessions.store import VolatileSessionStore


def test_session_store_keeps_metadata_and_redacts_debug_snapshot() -> None:
    store = VolatileSessionStore()

    store.set_session("synthetic-app", {"cookie": "session=secret-value"}, source="manual")

    assert store.get_metadata("synthetic-app")["source"] == "manual"  # type: ignore[index]
    snapshot = store.safe_debug_snapshot()
    assert snapshot["synthetic-app"]["headers"]["cookie"] == "[REDACTED]"  # type: ignore[index]
