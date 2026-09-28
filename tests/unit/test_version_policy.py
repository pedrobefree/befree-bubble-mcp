"""Main takes writes only in an app with no branch; live never does.

An app on a plan without branches has only test and live, and a blanket read-only main left it
with nowhere to write. The rule now follows the app, read from /appeditor/get_versions.
"""

from __future__ import annotations

from typing import Any

import pytest

from bubble_mcp.core.versions import MainVersionReadOnlyError
from bubble_mcp.execution import version_policy
from bubble_mcp.execution.client import BubbleEditorClient, HttpResponse
from bubble_mcp.sessions.store import BubbleSessionData

SESSION = BubbleSessionData(
    app_id="solo-app",
    url="https://bubble.io/page?id=solo-app&tab=Design&name=index",
    method="POST",
    headers={"cookie": "sid=1", "x-bubble-client-version": "abc"},
    cookies="sid=1",
    app_version="test",
    captured_at="2026-09-28T00:00:00Z",
    source="test",
)


def _versions(monkeypatch: pytest.MonkeyPatch, *branches: str, ok: bool = True) -> list[str]:
    calls: list[str] = []

    def fetch(session: BubbleSessionData, app_id: str) -> dict[str, Any]:
        calls.append(app_id)
        response = {"test": {"display": "Development"}, "live": {"display": "live"}}
        response.update({branch: {"display": f"{branch} name"} for branch in branches})
        return {"ok": ok, "status": 200 if ok else 401, "response": response if ok else None}

    version_policy.forget()
    monkeypatch.setattr(version_policy, "_fetch_versions", fetch)
    return calls


def test_an_app_without_branches_develops_on_test(monkeypatch: pytest.MonkeyPatch) -> None:
    _versions(monkeypatch)

    policy = version_policy.write_policy(SESSION, "solo-app")

    assert policy["main_writable"] is True
    assert policy["branches"] == []
    assert version_policy.main_write_allowed("test", SESSION, "solo-app")[0] is True
    assert version_policy.main_write_allowed("live", SESSION, "solo-app")[0] is False


def test_an_app_with_branches_keeps_main_read_only_and_suggests_a_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _versions(monkeypatch, "93k8b")

    policy = version_policy.write_policy(SESSION, "team-app")

    assert policy["main_writable"] is False
    assert policy["branches"] == ["93k8b"]
    assert "bubble_branch_create" in policy["advice"]
    assert "93k8b (93k8b name)" in policy["advice"]


def test_versions_that_cannot_be_read_keep_main_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _versions(monkeypatch, ok=False)

    assert version_policy.write_policy(SESSION, "solo-app")["main_writable"] is False
    assert version_policy.write_policy(None, "solo-app")["main_writable"] is False


def test_the_version_list_is_cached_until_forgotten(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _versions(monkeypatch)

    version_policy.write_policy(SESSION, "solo-app")
    version_policy.write_policy(SESSION, "solo-app")
    version_policy.forget("solo-app")
    version_policy.write_policy(SESSION, "solo-app")

    assert calls == ["solo-app", "solo-app"]


def _client(sent: list[str]) -> BubbleEditorClient:
    def transport(url: str, body: bytes, headers: dict[str, str], timeout: float) -> HttpResponse:
        sent.append(url)
        return HttpResponse(status=200, headers={}, body=b'{"last_change": "1"}')

    return BubbleEditorClient(transport=transport)


def _write(version: str) -> dict[str, Any]:
    return {"appname": "solo-app", "app_version": version, "changes": []}


def test_the_client_sends_a_test_write_in_an_app_without_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    _versions(monkeypatch)
    sent: list[str] = []

    _client(sent).write(_write("test"), SESSION)

    assert len(sent) == 1


def test_the_client_refuses_test_in_an_app_with_branches_and_live_always(monkeypatch: pytest.MonkeyPatch) -> None:
    _versions(monkeypatch, "93k8b")
    sent: list[str] = []

    with pytest.raises(MainVersionReadOnlyError, match="bubble_branch_create"):
        _client(sent).write(_write("test"), SESSION)
    _versions(monkeypatch)
    with pytest.raises(MainVersionReadOnlyError, match="live"):
        _client(sent).write(_write("live"), SESSION)
    assert sent == []


def test_the_tool_guard_follows_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.server import tools

    monkeypatch.setattr(tools, "load_session", lambda profile: SESSION)
    _versions(monkeypatch)
    assert tools.main_write_refusal("create_button", {"profile": "solo", "execute": True, "app_version": "test"}) is None

    _versions(monkeypatch, "93k8b")
    refusal = tools.main_write_refusal("create_button", {"profile": "solo", "execute": True, "app_version": "test"})
    assert refusal["error"] == "main_is_read_only"
    assert refusal["next_action"]["tool"] == "bubble_branch_create"

    live = tools.main_write_refusal("create_button", {"profile": "solo", "execute": True, "app_version": "live"})
    assert live["error"] == "main_is_read_only"


def test_the_session_check_tells_the_agent_where_it_may_write(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.server import tools

    monkeypatch.setattr(tools, "load_session", lambda profile: SESSION)
    monkeypatch.setattr(
        tools, "check_session", lambda profile, **kwargs: {"ok": True, "logged_in": True, "app_id": "solo-app"}
    )
    _versions(monkeypatch)

    result = tools.call_tool("bubble_session_check", {"profile": "solo"})

    assert result["write_policy"]["main_writable"] is True
    assert "test" in result["write_policy"]["advice"]


def test_creating_a_branch_drops_the_cached_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.server import tools

    calls = _versions(monkeypatch)
    version_policy.write_policy(SESSION, "solo-app")
    monkeypatch.setattr(tools, "create_bubble_branch", lambda **kwargs: {"ok": True})

    tools.call_tool("bubble_branch_create", {"profile": "solo", "name": "dev"})
    version_policy.write_policy(SESSION, "solo-app")

    assert calls == ["solo-app", "solo-app"]


def test_deleted_branches_and_live_copies_are_not_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    def fetch(session: BubbleSessionData, app_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "response": {
                "test": {},
                "live": {"readonly": True},
                "034rh": {"display": "unified", "deleted": True},
                "live.58422876584": {"readonly": True},
            },
        }

    version_policy.forget()
    monkeypatch.setattr(version_policy, "_fetch_versions", fetch)

    policy = version_policy.write_policy(SESSION, "solo-app")

    assert policy["branches"] == []
    assert policy["main_writable"] is True


def test_a_long_branch_list_is_cut_short_in_the_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    _versions(monkeypatch, *[f"b{index:02d}" for index in range(12)])

    advice = version_policy.write_policy(SESSION, "team-app")["advice"]

    assert "and 7 more" in advice
    assert "b11" not in advice
