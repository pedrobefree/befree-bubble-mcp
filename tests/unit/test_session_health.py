"""Know the session is logged out before spending calls on it.

No network: the probe is injected, and the gate's check is monkeypatched over the suite-wide
stub from conftest.
"""

from __future__ import annotations

from typing import Any

import pytest

from bubble_mcp.sessions import health
from bubble_mcp.sessions.store import BubbleSessionData


def _session(captured_at: str = "2026-09-28T00:00:00Z", headers: dict[str, str] | None = None) -> BubbleSessionData:
    return BubbleSessionData(
        app_id="mcp-test-app",
        url="https://bubble.io/page?id=mcp-test-app",
        method="POST",
        headers=headers if headers is not None else {"cookie": "b=1", "x-bubble-client-version": "abc"},
        cookies="b=1",
        app_version="test",
        captured_at=captured_at,
        source="browser",
    )


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    health.forget()


def _with_session(monkeypatch: pytest.MonkeyPatch, session: BubbleSessionData | None) -> None:
    monkeypatch.setattr(health, "load_session", lambda profile: session)


def test_a_200_with_fingerprints_is_logged_in_and_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(monkeypatch, _session())
    calls: list[Any] = []

    def probe(session: BubbleSessionData) -> dict[str, Any]:
        calls.append(session)
        return {"ok": True, "status": 200}

    first = health.check_session("mcp-test", probe=probe, monotonic=lambda: 100.0)
    second = health.check_session("mcp-test", probe=probe, monotonic=lambda: 200.0)
    stale = health.check_session("mcp-test", probe=probe, monotonic=lambda: 100.0 + health.LOGGED_IN_CACHE_SEC + 1)

    assert first["logged_in"] is True and first["cached"] is False
    assert second["logged_in"] is True and second["cached"] is True
    assert stale["cached"] is False
    assert len(calls) == 2


def test_a_401_is_logged_out_with_the_next_action_and_is_never_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(monkeypatch, _session())
    answers = iter([{"ok": False, "status": 401, "reason": "auth_blocked"}, {"ok": True, "status": 200}])

    out = health.check_session("mcp-test", probe=lambda session: next(answers))
    back = health.check_session("mcp-test", probe=lambda session: next(answers))

    assert out["logged_in"] is False
    assert out["reason"] == "expired"
    assert "bubble_session_login" in out["next_action"]
    assert back["logged_in"] is True


def test_a_new_login_is_not_answered_from_the_old_sessions_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(monkeypatch, _session("old"))
    health.check_session("mcp-test", probe=lambda session: {"ok": True})
    _with_session(monkeypatch, _session("new"))

    result = health.check_session("mcp-test", probe=lambda session: {"ok": False, "status": 401})

    assert result["logged_in"] is False


def test_an_html_answer_is_an_expired_session(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(monkeypatch, _session())

    def probe(session: BubbleSessionData) -> dict[str, Any]:
        raise RuntimeError("Bubble session expired: received HTML instead of JSON.")

    assert health.check_session("mcp-test", probe=probe)["reason"] == "expired"


def test_a_network_failure_is_unknown_not_logged_out(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(monkeypatch, _session())

    def probe(session: BubbleSessionData) -> dict[str, Any]:
        raise OSError("connection reset")

    result = health.check_session("mcp-test", probe=probe)

    assert result["logged_in"] is None
    assert result["reason"] == "check_failed"


def test_no_session_or_one_without_editor_headers_is_logged_out_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def probe(session: BubbleSessionData) -> dict[str, Any]:
        raise AssertionError("nothing to ask Bubble about")

    _with_session(monkeypatch, None)
    assert health.check_session("p", probe=probe)["reason"] == "no_session"
    _with_session(monkeypatch, _session(headers={"cookie": "b=1"}))
    assert health.check_session("p", probe=probe)["reason"] == "incomplete_session"


# --- the gate and the tool ------------------------------------------------------------------


def _gate(monkeypatch: pytest.MonkeyPatch, logged_in: bool | None) -> list[str]:
    checked: list[str] = []

    def check(profile: str, **kwargs: Any) -> dict[str, Any]:
        checked.append(profile)
        answer = {"ok": True, "profile": profile, "logged_in": logged_in, "reason": "expired"}
        if logged_in is False:
            answer["next_action"] = health.login_next_action(profile)
        return answer

    monkeypatch.setattr("bubble_mcp.server.tools.check_session", check)
    monkeypatch.setattr("bubble_mcp.server.tools.load_session", lambda profile: _session())
    return checked


def test_a_live_read_on_a_logged_out_session_is_refused_before_it_opens_a_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bubble_mcp.server.tools import call_tool

    _gate(monkeypatch, logged_in=False)

    def must_not_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a logged-out session must not reach the editor")

    monkeypatch.setattr("bubble_mcp.server.tools.read_live_node", must_not_run)

    result = call_tool("bubble_live_node_read", {"profile": "mcp-test", "pointer": ["api"]})

    assert result["ok"] is False
    assert result["error"] == "session_expired"
    assert "bubble_session_login" in result["next_action"]


def test_an_executed_catalog_write_is_gated_and_a_preview_or_local_tool_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bubble_mcp.server.tools import session_refusal

    checked = _gate(monkeypatch, logged_in=False)

    assert session_refusal("create_button", {"profile": "p", "execute": True})["error"] == "session_expired"
    assert session_refusal("create_button", {"profile": "p", "execute": False}) is None
    assert session_refusal("bubble_context_query", {"profile": "p"}) is None
    assert checked == ["p"]


def test_a_live_session_or_an_unknown_answer_lets_the_call_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.server.tools import session_refusal

    _gate(monkeypatch, logged_in=True)
    assert session_refusal("bubble_live_node_read", {"profile": "p"}) is None
    _gate(monkeypatch, logged_in=None)
    assert session_refusal("bubble_live_node_read", {"profile": "p"}) is None


def test_the_check_tool_is_exposed_read_only_and_asks_fresh_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.server.agent_catalog import tool_annotations
    from bubble_mcp.server.schemas import list_tool_schemas
    from bubble_mcp.server.tools import call_tool

    schema = {tool["name"]: tool for tool in list_tool_schemas()}["bubble_session_check"]
    assert schema["inputSchema"]["required"] == ["profile"]
    assert tool_annotations("bubble_session_check")["readOnlyHint"] is True

    seen: dict[str, Any] = {}

    def check(profile: str, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs, profile=profile)
        return {"ok": True, "logged_in": True}

    monkeypatch.setattr("bubble_mcp.server.tools.check_session", check)

    assert call_tool("bubble_session_check", {"profile": "mcp-test"})["logged_in"] is True
    assert seen == {"profile": "mcp-test", "use_cache": False}


def test_the_server_instructions_say_to_check_the_session_first() -> None:
    from bubble_mcp.server.instructions import SERVER_INSTRUCTIONS

    assert "bubble_session_check" in SERVER_INSTRUCTIONS
