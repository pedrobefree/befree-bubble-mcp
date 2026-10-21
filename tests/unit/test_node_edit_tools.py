"""The two live-node tools must be exposed, annotated, and routed."""

from __future__ import annotations

from typing import Any

from bubble_mcp.server.agent_catalog import tool_annotations
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.server.tools import call_tool


def _schema(name: str) -> dict[str, Any]:
    return {tool["name"]: tool for tool in list_tool_schemas()}[name]


def test_both_tools_are_exposed_with_their_required_arguments() -> None:
    read = _schema("bubble_live_node_read")
    edit = _schema("bubble_node_edit")

    assert read["inputSchema"]["required"] == ["profile", "pointer"]
    assert edit["inputSchema"]["required"] == ["profile", "pointer", "op"]
    assert edit["inputSchema"]["properties"]["op"]["enum"] == ["patch", "reorder"]


def test_the_read_tool_is_annotated_read_only_and_the_edit_tool_is_not() -> None:
    assert tool_annotations("bubble_live_node_read")["readOnlyHint"] is True
    assert tool_annotations("bubble_node_edit")["readOnlyHint"] is False


def test_the_edit_tool_defaults_to_preview() -> None:
    edit = _schema("bubble_node_edit")

    assert edit["inputSchema"]["properties"]["execute"]["default"] is False


def test_read_tool_routes_to_read_live_node(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_read(profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        seen.update({"profile": profile, "pointer": list(pointer), **kwargs})
        return {"ok": True, "pointer": list(pointer), "node": {"id": "act-1"}}

    monkeypatch.setattr("bubble_mcp.server.tools.read_live_node", fake_read)

    result = call_tool(
        "bubble_live_node_read", {"profile": "mcp-test", "pointer": ["api", "wf-1"]}
    )

    assert result["ok"] is True
    assert seen["profile"] == "mcp-test"
    assert seen["pointer"] == ["api", "wf-1"]


def test_read_tool_rejects_a_non_positive_read_timeout(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """timeout_ms=0 reads as no timeout at all to Playwright, so page.goto never gives up."""

    called: list[Any] = []

    def fake_read(profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        called.append((profile, pointer, kwargs))
        return {"ok": True, "pointer": list(pointer), "node": {"id": "act-1"}}

    monkeypatch.setattr("bubble_mcp.server.tools.read_live_node", fake_read)

    result = call_tool(
        "bubble_live_node_read",
        {"profile": "mcp-test", "pointer": ["api", "wf-1"], "read_timeout_sec": 0},
    )

    assert result == {
        "ok": False,
        "error": "invalid_read_timeout_sec",
        "message": "read_timeout_sec must be a positive number of seconds; got 0.",
    }
    assert called == []


def test_edit_tool_routes_to_edit_live_node(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_edit(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True, "execute": False}

    monkeypatch.setattr("bubble_mcp.server.tools.edit_live_node", fake_edit)

    call_tool(
        "bubble_node_edit",
        {
            "profile": "mcp-test",
            "pointer": ["api", "wf-1", "actions", "0"],
            "op": "patch",
            "leaf_pointer": ["properties"],
            "patch": {"param_id": "Order"},
        },
    )

    assert seen["op"] == "patch"
    assert seen["execute"] is False
    assert seen["leaf_pointer"] == ["properties"]


def test_edit_tool_requires_a_profile() -> None:
    try:
        call_tool("bubble_node_edit", {"pointer": ["api"], "op": "patch"})
    except ValueError as error:
        assert "profile" in str(error)
    else:
        raise AssertionError("a missing profile must not reach the editor")


def test_the_workflow_guidance_routes_editing_to_the_new_tool() -> None:
    from bubble_mcp.server.agent_guide import ROUTES

    route = next(r for r in ROUTES if r["intent"] == "manage_workflows")

    assert "bubble_node_edit" in route["notes"]
    assert "bubble_node_edit" in route["tools"]
    assert "bubble_live_node_read" in route["tools"]


def test_edit_tool_records_a_mutation_overlay_for_an_executed_write(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Without this, bubble_context_summary keeps serving pre-edit state after a real write."""

    recorded: dict[str, Any] = {}
    payload = {"appname": "mcp-test-app", "changes": [{"path_array": ["api", "wf-1"]}]}

    def fake_edit(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "execute": True,
            "verified": True,
            "write": {"ok": True, "request": {"payload": payload}, "response": {"status": "ok"}},
        }

    monkeypatch.setattr("bubble_mcp.server.tools.edit_live_node", fake_edit)
    monkeypatch.setattr(
        "bubble_mcp.server.tools.record_mutation_overlay",
        lambda **kwargs: recorded.update(kwargs),
    )

    call_tool(
        "bubble_node_edit",
        {
            "profile": "mcp-test",
            "pointer": ["api", "wf-1", "actions", "0"],
            "op": "patch",
            "leaf_pointer": ["properties"],
            "patch": {"param_id": "Order"},
            "execute": True,
        },
    )

    assert recorded["source"] == "bubble_node_edit"
    assert recorded["profile"] == "mcp-test"
    assert recorded["app_id"] == "mcp-test-app"
    assert recorded["payload"] is payload
    assert recorded["response"] == {"status": "ok"}


def test_edit_tool_records_nothing_for_a_preview(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    recorded: list[Any] = []

    monkeypatch.setattr(
        "bubble_mcp.server.tools.edit_live_node",
        lambda **kwargs: {
            "ok": True,
            "execute": False,
            "write": {"ok": True, "dry_run": True, "request": {"payload": {"changes": []}}},
        },
    )
    monkeypatch.setattr(
        "bubble_mcp.server.tools.record_mutation_overlay",
        lambda **kwargs: recorded.append(kwargs),
    )

    call_tool(
        "bubble_node_edit",
        {
            "profile": "mcp-test",
            "pointer": ["api", "wf-1", "actions", "0"],
            "op": "patch",
            "leaf_pointer": ["properties"],
            "patch": {"param_id": "Order"},
        },
    )

    assert recorded == []


def test_edit_tool_forwards_app_version_instead_of_dropping_it(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The schema advertises app_version; a dropped one reads test and writes the branch."""

    seen: dict[str, Any] = {}

    def fake_edit(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True, "execute": False}

    monkeypatch.setattr("bubble_mcp.server.tools.edit_live_node", fake_edit)

    call_tool(
        "bubble_node_edit",
        {
            "profile": "mcp-test",
            "pointer": ["api", "wf-1", "actions", "0"],
            "op": "patch",
            "leaf_pointer": ["properties"],
            "patch": {"param_id": "Order"},
            "app_version": "my-branch",
        },
    )

    assert seen["app_version"] == "my-branch"


def test_the_edit_tool_description_says_verified_is_not_a_render_check() -> None:
    description = _schema("bubble_node_edit")["description"]

    assert "render_unverified" in description
    assert "actions" in description


def test_the_workflow_guidance_mentions_the_reorder_op() -> None:
    from bubble_mcp.server.agent_guide import ROUTES

    route = next(r for r in ROUTES if r["intent"] == "manage_workflows")

    assert "reorder" in route["notes"]
