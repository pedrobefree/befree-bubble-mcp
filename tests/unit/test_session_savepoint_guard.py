"""The savepoint guard runs before a session's first executed write, and never blocks one."""

from __future__ import annotations

from typing import Any

from bubble_mcp.execution.session_savepoint import (
    ensure_session_savepoint as real_ensure_session_savepoint,
)
from bubble_mcp.server.tools import call_tool, savepoint_guard_report


def _record_calls(monkeypatch, calls: list[dict[str, Any]]) -> None:  # type: ignore[no-untyped-def]
    def fake_ensure(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"created": True, "savepoint": {"message": kwargs.get("message")}}

    monkeypatch.setattr("bubble_mcp.server.tools.ensure_session_savepoint", fake_ensure)


def test_an_executed_write_takes_a_savepoint_first(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []
    _record_calls(monkeypatch, calls)

    report = savepoint_guard_report(
        "create_text", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    )

    assert len(calls) == 1
    assert calls[0]["profile"] == "mcp-test"
    assert calls[0]["app_id"] == "mcp-test-app"
    assert report is not None and report["created"] is True


def test_a_preview_takes_no_savepoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []
    _record_calls(monkeypatch, calls)

    report = savepoint_guard_report(
        "create_text", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": False}
    )

    assert calls == []
    assert report is None


def test_a_read_only_tool_takes_no_savepoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []
    _record_calls(monkeypatch, calls)

    report = savepoint_guard_report(
        "list_events", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    )

    assert calls == []
    assert report is None


def test_the_savepoint_tools_themselves_take_no_savepoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Otherwise restoring one would first create another, on top of what is being undone."""

    calls: list[dict[str, Any]] = []
    _record_calls(monkeypatch, calls)

    for tool in ("bubble_savepoint_create", "bubble_savepoint_restore"):
        assert savepoint_guard_report(tool, {"profile": "mcp-test", "execute": True}) is None
    assert calls == []


def test_the_message_names_the_tool_that_is_about_to_run(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []
    _record_calls(monkeypatch, calls)

    savepoint_guard_report(
        "delete_group", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    )

    assert "delete_group" in calls[0]["message"]


def test_a_write_with_no_profile_takes_no_savepoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []
    _record_calls(monkeypatch, calls)

    assert savepoint_guard_report("create_text", {"execute": True}) is None
    assert calls == []


def test_a_guard_failure_never_reaches_the_caller_as_a_raise(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def exploding(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("config unreadable")

    monkeypatch.setattr("bubble_mcp.server.tools.ensure_session_savepoint", exploding)

    report = savepoint_guard_report(
        "create_text", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    )

    assert report is not None
    assert "config unreadable" in report["error"]


def test_the_report_is_attached_to_the_tool_result(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []
    _record_calls(monkeypatch, calls)
    monkeypatch.setattr(
        "bubble_mcp.server.tools.dispatch_aria_runtime_tool",
        lambda name, args: {"ok": True, "executed": True, "results": []},
    )

    result = call_tool(
        "create_text", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    )

    assert result["session_savepoint"]["created"] is True


def test_two_writes_in_one_process_share_a_single_savepoint(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The guard's session identity must be stable, or every write takes its own savepoint.

    This exercises the real ensure_session_savepoint, so a per-call session id shows up here as
    two savepoints where the design calls for one.
    """

    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    created: list[str] = []

    def fake_create_savepoint(**kwargs):  # type: ignore[no-untyped-def]
        created.append(kwargs["message"])
        return {"ok": True, "executed": True}

    # conftest stubs ensure_session_savepoint for the whole suite so no test reaches the network.
    # This one is about that function's own logic, so put the real one back and stub only the
    # call that would leave the machine.
    monkeypatch.setattr(
        "bubble_mcp.server.tools.ensure_session_savepoint", real_ensure_session_savepoint
    )
    monkeypatch.setattr("bubble_mcp.server.tools.create_savepoint", fake_create_savepoint)

    args = {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    savepoint_guard_report("create_text", dict(args))
    savepoint_guard_report("delete_group", dict(args))

    assert len(created) == 1


def _never_dispatch(monkeypatch, ran: list[str]) -> None:  # type: ignore[no-untyped-def]
    def fake_dispatch(name, args):  # type: ignore[no-untyped-def]
        ran.append(name)
        return {"ok": True, "executed": True, "results": []}

    monkeypatch.setattr("bubble_mcp.server.tools.dispatch_aria_runtime_tool", fake_dispatch)


def test_a_write_still_runs_when_its_savepoint_could_not_be_taken(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A savepoint marks a session; losing it must not stop an author editing their own app."""

    ran: list[str] = []
    _never_dispatch(monkeypatch, ran)
    monkeypatch.setattr(
        "bubble_mcp.server.tools.ensure_session_savepoint",
        lambda **kwargs: {"created": False, "error": "editor unreachable"},
    )

    result = call_tool(
        "create_text", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    )

    assert ran == ["create_text"]
    assert result["ok"] is True
    assert result["session_savepoint"]["error"] == "editor unreachable"


def test_an_existing_session_savepoint_is_not_a_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The second write of a session creates nothing and must still be allowed to run."""

    ran: list[str] = []
    _never_dispatch(monkeypatch, ran)
    monkeypatch.setattr(
        "bubble_mcp.server.tools.ensure_session_savepoint",
        lambda **kwargs: {"created": False, "reason": "session_savepoint_exists"},
    )

    result = call_tool(
        "create_text", {"profile": "mcp-test", "app_id": "mcp-test-app", "execute": True}
    )

    assert ran == ["create_text"]
    assert result["ok"] is True
