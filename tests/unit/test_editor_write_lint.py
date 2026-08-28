"""Bug 7 (the client report): bubble_editor_write accepted decoded keys in node bodies.

Bubble's internal app tree uses encoded keys (%x=type, %p=properties, %nm=name,
%dn=default_name). The .bubble export is the DECODED form. Bodies written with
decoded keys at node positions (%el/%wf/actions) get HTTP 200 and even survive
re-export, but the editor renders them as "[missing: null]".
"""

from __future__ import annotations

from bubble_mcp.execution.write_lint import lint_editor_write_changes


def _change(path, body):
    return {"path_array": path, "body": body}


def test_decoded_action_body_is_flagged() -> None:
    issues = lint_editor_write_changes(
        [
            _change(
                ["%p3", "bTVso", "%wf", "bTZRe", "actions", "7"],
                {"id": "b5VD1", "type": "SetCustomState", "properties": {"custom_state": "x"}},
            )
        ]
    )
    assert len(issues) == 1
    assert "type" in issues[0] and "%x" in issues[0]


def test_decoded_element_body_is_flagged() -> None:
    issues = lint_editor_write_changes(
        [
            _change(
                ["%p3", "pg1", "%el", "el1"],
                {"id": "el1", "type": "CustomElement", "default_name": "A", "properties": {"order": 1}},
            )
        ]
    )
    assert len(issues) == 1


def test_encoded_bodies_pass() -> None:
    issues = lint_editor_write_changes(
        [
            _change(
                ["%p3", "bTVso", "%wf", "bTZRe", "actions", "7"],
                {"id": "b5VD1", "%x": "SetCustomState", "%p": {"custom_state": "x"}},
            ),
            _change(["%p3", "pg1", "%el", "el1", "%nm"], "My Name"),
        ]
    )
    assert issues == []


def test_non_node_paths_with_friendly_keys_pass() -> None:
    issues = lint_editor_write_changes(
        [
            _change(
                ["settings", "client_safe", "apiconnector2", "col1", "calls", "call1"],
                {"%nm": "Get Products", "method": "get", "publish_as": "data"},
            ),
            _change(["_index", "id_to_path", "abc"], "%p3.pg1.%el.el1"),
        ]
    )
    assert issues == []


def test_editor_write_tool_rejects_decoded_bodies(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    from bubble_mcp.server import tools as tools_module
    from bubble_mcp.sessions.store import BubbleSessionData

    monkeypatch.setattr(
        tools_module,
        "load_session",
        lambda profile: BubbleSessionData(app_id="app-x", url="https://bubble.io/page?id=app-x", method="POST", headers={}, cookies="k=v", app_version="test", captured_at="2026-08-24T00:00:00Z", source="test"),
    )

    result = tools_module.call_tool(
        "bubble_editor_write",
        {
            "profile": "p1",
            "execute": False,
            "payload": {
                "appname": "app-x",
                "changes": [
                    {
                        "path_array": ["%p3", "bTVso", "%wf", "bTZRe", "actions", "7"],
                        "body": {"id": "b5VD1", "type": "SetCustomState", "properties": {}},
                        "intent": {"name": "SetData"},
                    }
                ],
            },
        },
    )
    assert result["ok"] is False
    assert result["error"] == "decoded_keys_in_node_body"
    assert result["issues"]
    assert "allow_decoded_keys" in result["message"]


def test_expression_nodes_produce_warning_not_rejection() -> None:
    """Bug 8: expression encodings (APIEventParameter, Message chains, param_id) are NOT
    derivable from the export, and /appeditor/write returns 200 for any body. Hand-composed
    expression nodes must at least warn: 200 is not success, prefer captured payloads."""

    from bubble_mcp.execution.write_lint import lint_expression_warnings

    action_with_expression = {
        "path_array": ["%p3", "bTVso", "%wf", "bTbgi", "actions", "3"],
        "body": {
            "id": "a1",
            "%x": "MakeChangesToThing",
            "%p": {
                "to_change": {"%x": "APIEventParameter", "%p": {"param_id": "bTbgp"}},
                "condition": {"%x": "Message", "%p": {"name": "is_not_empty"}},
            },
        },
    }
    warnings = lint_expression_warnings([action_with_expression])
    # one generic hand-composed-expression warning + one incomplete-APIEventParameter warning
    assert len(warnings) == 2
    assert any("200" in w for w in warnings)
    assert any("btype_id" in w for w in warnings)

    plain_action = {
        "path_array": ["%p3", "bTVso", "%wf", "bTbgi", "actions", "4"],
        "body": {"id": "a2", "%x": "ShowElement", "%p": {"element_id": "el1"}},
    }
    assert lint_expression_warnings([plain_action]) == []

    non_node = {
        "path_array": ["settings", "client_safe", "apiconnector2", "c1"],
        "body": {"%x": "Message"},
    }
    assert lint_expression_warnings([non_node]) == []


def test_editor_write_result_carries_expression_warnings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    from bubble_mcp.server import tools as tools_module
    from bubble_mcp.sessions.store import BubbleSessionData

    monkeypatch.setattr(
        tools_module,
        "load_session",
        lambda profile: BubbleSessionData(app_id="app-x", url="u", method="POST", headers={}, cookies="k=v", app_version="test", captured_at="2026-08-24T00:00:00Z", source="test"),
    )
    result = tools_module.call_tool(
        "bubble_editor_write",
        {
            "profile": "p1",
            "execute": False,
            "payload": {
                "appname": "app-x",
                "changes": [
                    {
                        "path_array": ["%p3", "pg", "%wf", "wf1", "actions", "0"],
                        "body": {"id": "a1", "%x": "SetState", "%p": {"value": {"%x": "PreviousStep", "%p": {}}}},
                        "intent": {"name": "SetData"},
                    }
                ],
            },
        },
    )
    assert result.get("warnings"), "expression warning must surface in the tool result"


def test_incomplete_api_event_parameter_is_flagged() -> None:
    """Root cause of the the client report, bug-8 failures: APIEventParameter resolves only with
    btype_id + event_id + param_id + param_name together (confirmed against live editor
    memory raw). A node missing the type context renders as an unresolved parameter."""

    from bubble_mcp.execution.write_lint import lint_expression_warnings

    incomplete = {
        "path_array": ["%p3", "x", "%wf", "wf1", "actions", "0"],
        "body": {
            "id": "a1",
            "%x": "ChangeThing",
            "%p": {"to_change": {"type": "APIEventParameter", "properties": {"param_id": "bTbgp"}}},
        },
    }
    warnings = lint_expression_warnings([incomplete])
    assert any("btype_id" in w and "event_id" in w for w in warnings), warnings

    complete = {
        "path_array": ["%p3", "x", "%wf", "wf1", "actions", "1"],
        "body": {
            "id": "a2",
            "%x": "ChangeThing",
            "%p": {
                "to_change": {
                    "type": "APIEventParameter",
                    "is_slidable": False,
                    "properties": {
                        "btype_id": "custom.client",
                        "event_id": "bTbgi",
                        "param_id": "Client",
                        "param_name": "Client",
                    },
                }
            },
        },
    }
    complete_warnings = lint_expression_warnings([complete])
    assert not any("btype_id" in w for w in complete_warnings), complete_warnings


def test_invalid_background_style_value_is_flagged() -> None:
    """Root cause of the mcp-test-app landing page report: the catalog enum exposes
    "color" for flat backgrounds while the editor stores "bgcolor". Writing "color"
    returns HTTP 200 and then shows up as "<element> - is not a possible option"
    in the Issue Checker."""

    from bubble_mcp.execution.write_lint import lint_enum_warnings

    create = {
        "path_array": ["%p3", "page", "%el", "bXYZ"],
        "body": {"%x": "Group", "%dn": "gp_tasks", "%p": {"%bas": "color", "%bgc": "#FFFFFF"}},
    }
    set_data = {
        "path_array": ["%p3", "page", "%el", "bXYZ", "%p", "%bas"],
        "body": "color",
    }
    for change in (create, set_data):
        warnings = lint_enum_warnings([change])
        assert any("bgcolor" in w for w in warnings), (change, warnings)

    ok = {
        "path_array": ["%p3", "page", "%el", "bXYZ", "%p", "%bas"],
        "body": "bgcolor",
    }
    assert lint_enum_warnings([ok]) == []
