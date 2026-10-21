"""One savepoint per session, not per edit.

Per-edit savepoints would put one entry in Bubble's restore history for every write, making the
history unreadable exactly when someone needs to find the good point in it.
"""

from __future__ import annotations

import json
from typing import Any

from bubble_mcp.execution.session_savepoint import (
    ensure_session_savepoint,
    session_savepoint_path,
)


def _creator(calls: list[str], *, ok: bool = True):  # type: ignore[no-untyped-def]
    def create(*, message: str) -> dict[str, Any]:
        calls.append(message)
        return {"ok": ok, "executed": True, "message": message}

    return create


def test_the_first_write_of_a_session_creates_a_savepoint(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[str] = []

    result = ensure_session_savepoint(
        profile="dev",
        app_id="mcp-test-app",
        app_version="test",
        session_id="s-1",
        message="add a login workflow",
        now=1000.0,
        create=_creator(calls),
    )

    assert calls == ["add a login workflow"]
    assert result is not None and result["created"] is True
    marker = json.loads(session_savepoint_path("dev", "mcp-test-app").read_text(encoding="utf-8"))
    assert marker["session_id"] == "s-1"


def test_a_later_write_in_the_same_session_creates_nothing(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[str] = []
    common = dict(
        profile="dev",
        app_id="mcp-test-app",
        app_version="test",
        session_id="s-1",
        create=_creator(calls),
    )

    ensure_session_savepoint(message="first", now=1000.0, **common)
    result = ensure_session_savepoint(message="second", now=1060.0, **common)

    assert calls == ["first"]
    assert result is not None and result["created"] is False


def test_a_different_session_opens_a_new_savepoint(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[str] = []

    ensure_session_savepoint(
        profile="dev", app_id="mcp-test-app", app_version="test", session_id="s-1",
        message="first", now=1000.0, create=_creator(calls),
    )
    ensure_session_savepoint(
        profile="dev", app_id="mcp-test-app", app_version="test", session_id="s-2",
        message="second", now=1060.0, create=_creator(calls),
    )

    assert calls == ["first", "second"]


def test_an_idle_gap_opens_a_new_savepoint_even_in_the_same_session(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[str] = []
    common = dict(
        profile="dev",
        app_id="mcp-test-app",
        app_version="test",
        session_id="s-1",
        idle_seconds=1800,
        create=_creator(calls),
    )

    ensure_session_savepoint(message="first", now=1000.0, **common)
    ensure_session_savepoint(message="after a long pause", now=1000.0 + 1801, **common)

    assert calls == ["first", "after a long pause"]


def test_a_second_app_gets_its_own_savepoint(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[str] = []

    ensure_session_savepoint(
        profile="dev", app_id="app-one", app_version="test", session_id="s-1",
        message="first", now=1000.0, create=_creator(calls),
    )
    ensure_session_savepoint(
        profile="dev", app_id="app-two", app_version="test", session_id="s-1",
        message="second", now=1010.0, create=_creator(calls),
    )

    assert calls == ["first", "second"]


def test_a_failed_savepoint_is_retried_on_the_next_write(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A marker written for a savepoint that never landed would silently skip protection."""

    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    failed: list[str] = []
    succeeded: list[str] = []

    first = ensure_session_savepoint(
        profile="dev", app_id="mcp-test-app", app_version="test", session_id="s-1",
        message="first", now=1000.0, create=_creator(failed, ok=False),
    )
    ensure_session_savepoint(
        profile="dev", app_id="mcp-test-app", app_version="test", session_id="s-1",
        message="second", now=1010.0, create=_creator(succeeded),
    )

    assert first is not None and first["created"] is False
    assert succeeded == ["second"]
    assert not session_savepoint_path("dev", "mcp-test-app").exists() or json.loads(
        session_savepoint_path("dev", "mcp-test-app").read_text(encoding="utf-8")
    )["message"] == "second"


def test_a_raising_savepoint_never_blocks_the_write(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The savepoint is a safety net; losing it must not stop the work it was protecting."""

    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    def exploding(*, message: str) -> dict[str, Any]:
        raise RuntimeError("editor unreachable")

    result = ensure_session_savepoint(
        profile="dev", app_id="mcp-test-app", app_version="test", session_id="s-1",
        message="first", now=1000.0, create=exploding,
    )

    assert result is not None
    assert result["created"] is False
    assert "editor unreachable" in result["error"]


def test_the_idle_window_measures_time_since_the_last_write_not_the_first(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A long session of steady work is one session, not a new one every 30 minutes."""

    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[str] = []
    common = dict(
        profile="dev",
        app_id="mcp-test-app",
        app_version="test",
        session_id="s-1",
        idle_seconds=1800,
        create=_creator(calls),
    )

    ensure_session_savepoint(message="first", now=1000.0, **common)
    ensure_session_savepoint(message="kept working", now=1000.0 + 1700, **common)
    ensure_session_savepoint(message="still working", now=1000.0 + 3400, **common)

    assert calls == ["first"]


def test_a_real_idle_gap_since_the_last_write_opens_a_new_savepoint(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[str] = []
    common = dict(
        profile="dev",
        app_id="mcp-test-app",
        app_version="test",
        session_id="s-1",
        idle_seconds=1800,
        create=_creator(calls),
    )

    ensure_session_savepoint(message="first", now=1000.0, **common)
    ensure_session_savepoint(message="kept working", now=1000.0 + 1700, **common)
    ensure_session_savepoint(message="back after lunch", now=1000.0 + 1700 + 1801, **common)

    assert calls == ["first", "back after lunch"]
