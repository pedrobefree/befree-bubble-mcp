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
    assert edit["inputSchema"]["properties"]["op"]["enum"] == ["patch", "reorder", "remove"]


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
    """timeout_ms=0 reads as no timeout at all to Playwright, so page.goto never gives up.

    WHICH PATH THIS COVERS. The schema declares read_timeout_sec with minimum=10, so an MCP host
    that validates arguments rejects 0 before the tool ever runs - a second app's session
    confirmed this (a second app's capture report, 2026-08-27, section 2.3). This exercises
    call_tool directly, which is the path cli/main.py takes: no schema, no validation, and the
    guard is the only thing standing between a typo and a page.goto that never returns.
    """

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


def test_the_clone_tool_is_exposed_and_defaults_to_preview() -> None:
    clone = _schema("bubble_clone_workflow")

    assert clone["inputSchema"]["required"] == ["profile", "pointer"]
    assert clone["inputSchema"]["properties"]["execute"]["default"] is False


def test_the_clone_tool_is_not_annotated_read_only() -> None:
    assert "bubble_clone_workflow" in {tool["name"] for tool in list_tool_schemas()}
    assert tool_annotations("bubble_clone_workflow")["readOnlyHint"] is False


def test_clone_tool_routes_to_clone_live_workflow(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_clone(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True, "new_pointer": ["api", "new"]}

    monkeypatch.setattr("bubble_mcp.server.tools.clone_live_workflow", fake_clone)

    result = call_tool(
        "bubble_clone_workflow",
        {"profile": "mcp-test", "pointer": ["api", "wf-1"], "wf_name": "wf_copy"},
    )

    assert result["ok"] is True
    assert seen["profile"] == "mcp-test"
    assert seen["pointer"] == ["api", "wf-1"]
    assert seen["wf_name"] == "wf_copy"
    assert seen["execute"] is False


def test_clone_tool_refuses_an_empty_pointer() -> None:
    try:
        call_tool("bubble_clone_workflow", {"profile": "mcp-test", "pointer": []})
    except ValueError as error:
        assert "pointer" in str(error)
    else:
        raise AssertionError("a clone with no source pointer must not reach the editor")


def test_the_three_savepoint_tools_are_exposed() -> None:
    names = {tool["name"] for tool in list_tool_schemas()}

    assert {"bubble_savepoint_create", "bubble_savepoint_list", "bubble_savepoint_restore"} <= names


def test_the_savepoint_list_tool_is_read_only_and_the_others_are_not() -> None:
    assert tool_annotations("bubble_savepoint_list")["readOnlyHint"] is True
    assert tool_annotations("bubble_savepoint_create")["readOnlyHint"] is False
    assert tool_annotations("bubble_savepoint_restore")["readOnlyHint"] is False


def test_the_restore_tool_requires_a_timestamp_and_defaults_to_preview() -> None:
    restore = _schema("bubble_savepoint_restore")

    assert restore["inputSchema"]["required"] == ["profile", "timestamp"]
    assert restore["inputSchema"]["properties"]["execute"]["default"] is False
    assert restore["inputSchema"]["properties"]["confirm"]["default"] is False


def test_savepoint_create_routes_to_create_savepoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_create(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True, "executed": True}

    monkeypatch.setattr("bubble_mcp.server.tools.create_savepoint", fake_create)

    result = call_tool(
        "bubble_savepoint_create",
        {"profile": "mcp-test", "message": "before the login work", "execute": True},
    )

    assert result["ok"] is True
    assert seen["message"] == "before the login work"
    assert seen["execute"] is True


def test_savepoint_restore_passes_confirm_through(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_restore(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True, "executed": True}

    monkeypatch.setattr("bubble_mcp.server.tools.restore_to_timestamp", fake_restore)

    call_tool(
        "bubble_savepoint_restore",
        {"profile": "mcp-test", "timestamp": 1787834752581, "execute": True, "confirm": True},
    )

    assert seen["timestamp"] == 1787834752581
    assert seen["confirm"] is True


def test_savepoint_restore_refuses_a_missing_timestamp() -> None:
    try:
        call_tool("bubble_savepoint_restore", {"profile": "mcp-test"})
    except ValueError as error:
        assert "timestamp" in str(error)
    else:
        raise AssertionError("restoring without an instant must not reach Bubble")


def test_the_deploy_preview_tool_is_exposed_and_read_only() -> None:
    preview = _schema("bubble_deploy_preview")

    assert preview["inputSchema"]["required"] == ["profile"]
    assert preview["inputSchema"]["properties"]["source"]["enum"] == ["overlay", "full_scan"]
    assert tool_annotations("bubble_deploy_preview")["readOnlyHint"] is True


def test_deploy_preview_routes_with_the_overlay_and_the_http_reader(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    monkeypatch.setattr(
        "bubble_mcp.server.tools.read_mutation_overlay",
        lambda profile, app_id: {"entries": [{"changes": [{"path_array": ["api", "wf-1"]}]}]},
    )

    def fake_preview(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True, "changes": []}

    monkeypatch.setattr("bubble_mcp.server.tools.preview_deploy", fake_preview)

    result = call_tool(
        "bubble_deploy_preview",
        {"profile": "mcp-test", "app_id": "mcp-test-app", "source": "full_scan"},
    )

    assert result["ok"] is True
    assert seen["source"] == "full_scan"
    assert seen["overlay"]["entries"][0]["changes"][0]["path_array"] == ["api", "wf-1"]
    assert seen["reader"] is not None


def test_the_edit_tool_offers_remove_alongside_patch_and_reorder() -> None:
    edit = _schema("bubble_node_edit")

    assert edit["inputSchema"]["properties"]["op"]["enum"] == ["patch", "reorder", "remove"]
    assert "keys" in edit["inputSchema"]["properties"]


def test_edit_tool_passes_keys_through_for_a_remove(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_edit(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("bubble_mcp.server.tools.edit_live_node", fake_edit)

    call_tool(
        "bubble_node_edit",
        {
            "profile": "mcp-test",
            "pointer": ["api", "wf-1", "actions", "0"],
            "op": "remove",
            "leaf_pointer": ["%p", "%co"],
            "keys": ["1"],
        },
    )

    assert seen["op"] == "remove"
    assert seen["keys"] == ["1"]
