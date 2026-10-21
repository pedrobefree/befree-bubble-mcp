"""The MCP dispatcher must preserve the version selected by sessions and E2E suites."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, get_config_dir, save_settings
from bubble_mcp.e2e.paths import suite_path
from bubble_mcp.execution import node_edit
from bubble_mcp.server import tools
from bubble_mcp.sessions.store import save_session, session_from_payload


def _profile(version: str | None) -> None:
    save_settings(BubbleMcpSettings(get_config_dir(), "p", {"p": BubbleProfile("p", "synthetic", "synthetic", app_version=version)}))


def _suite(branch: str) -> Path:
    path = suite_path("p", "smoke")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "smoke", "profile": "p", "app_id": "synthetic", "branch": branch,
                               "base_url": "https://synthetic.bubbleapps.io", "run_as": {"user_id": "user"},
                               "cases": [{"id": "case1", "module": "case1.py"}]}))
    return path


@pytest.mark.parametrize(("profile_version", "session_version", "explicit", "execute", "want"), [
    (None, "session-branch", None, True, "session-branch"),
    (None, "session-branch", None, False, "session-branch"),
    ("profile-branch", "session-branch", None, True, "profile-branch"),
    ("profile-branch", "session-branch", "call-branch", True, "call-branch"),
    (None, "session-branch", "call-branch", False, "call-branch"),
    (None, "", None, False, "test"),
])
def test_clone_reads_writes_and_savepoint_use_the_selected_version(
    monkeypatch: pytest.MonkeyPatch, profile_version: str | None, session_version: str,
    explicit: str | None, execute: bool, want: str,
) -> None:
    _profile(profile_version)
    save_session("p", session_from_payload({"app_id": "synthetic", "app_version": session_version}))
    nodes: dict[tuple[str, ...], Any] = {
        ("api", "source"): {"id": "old-event", "%x": "APIEvent", "actions": {}},
        ("_index", "id_to_path"): {"old-event": "api.source"},
    }
    reads: list[str] = []
    writes: list[dict[str, Any]] = []
    savepoints: list[str] = []

    def read(profile: str, pointer: list[str], **kwargs: Any) -> dict[str, Any]:
        reads.append(kwargs["app_version"])
        key = tuple(pointer)
        return {"ok": True, "node": copy.deepcopy(nodes[key]), "app_id": "synthetic"} if key in nodes else {"ok": False, "error": "pointer_not_found"}

    def write(self: Any, payload: dict[str, Any], session: Any, **kwargs: Any) -> dict[str, Any]:
        writes.append(payload)
        if not kwargs["dry_run"]:
            for change in payload["changes"]:
                nodes[tuple(change["path_array"])] = copy.deepcopy(change["body"])
        return {"ok": True, "dry_run": kwargs["dry_run"], "request": {"payload": payload}}

    def savepoint(**kwargs: Any) -> dict[str, Any]:
        savepoints.append(kwargs["app_version"])
        return {"created": False, "reason": "synthetic"}

    monkeypatch.setattr(node_edit, "read_live_node", read)
    monkeypatch.setattr(node_edit.BubbleEditorClient, "write", write)
    monkeypatch.setattr(tools, "ensure_session_savepoint", savepoint)
    args: dict[str, Any] = {"profile": "p", "pointer": ["api", "source"], "execute": execute}
    if explicit is not None:
        args["app_version"] = explicit
    result = tools.call_tool("bubble_clone_workflow", args)
    assert result["ok"] is True
    assert writes[0]["app_version"] == want
    assert set(reads) == {want}
    assert savepoints == ([want] if execute else [])
    if execute:
        assert result["verified"] is True


@pytest.mark.parametrize(("profile_version", "suite_branch", "overrides", "want"), [
    ("test", "suite-branch", {}, "suite-branch"),
    ("profile-branch", "suite-branch", {}, "suite-branch"),
    ("live", "suite-branch", {}, "suite-branch"),
    ("profile-branch", "", {}, "profile-branch"),
    ("profile-branch", "suite-branch", {"app_version": "call-branch"}, "call-branch"),
    ("profile-branch", "suite-branch", {"branch": "call-branch"}, "call-branch"),
    ("profile-branch", "suite-branch", {"branch": "call-branch", "app_version": "alias-branch"}, "call-branch"),
    ("test", "suite-branch", {"app_version": ""}, "suite-branch"),
    ("test", "suite-branch", {"app_version": "  "}, "suite-branch"),
])
def test_e2e_dispatch_preserves_suite_branch_unless_caller_overrides(
    profile_version: str, suite_branch: str, overrides: dict[str, str], want: str,
) -> None:
    _profile(profile_version)
    _suite(suite_branch)
    result = tools.call_tool("bubble_e2e_run", {"profile": "p", "suite": "smoke", "execute": False, **overrides})
    assert result.get("target", {}).get("branch") == want
    assert result["target"]["base_url"] == f"https://synthetic.bubbleapps.io/version-{want}"
    assert result["mode"] == "preview"
    assert result["results"] == []


@pytest.mark.parametrize(("overrides", "want"), [
    ({}, "suite-branch"),
    ({"app_version": "call-branch"}, "call-branch"),
    ({"branch": "call-branch"}, "call-branch"),
    ({"app_version": ""}, "suite-branch"),
])
def test_extending_e2e_suite_does_not_replace_its_branch_with_profile_default(
    overrides: dict[str, str], want: str,
) -> None:
    _profile("test")
    path = _suite("suite-branch")
    result = tools.call_tool("bubble_e2e_scaffold", {"profile": "p", "suite": "smoke", "case_id": "case2", "execute": True, **overrides})
    assert result["ok"] is True
    stored = json.loads(path.read_text())
    assert stored["branch"] == want
    assert [case["id"] for case in stored["cases"]] == ["case1", "case2"]
