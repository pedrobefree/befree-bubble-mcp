import json

from bubble_mcp.server.stdio import handle_request
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.sessions.store import BubbleSessionData, save_session


def first_change(payload: dict, intent_name: str) -> dict:  # type: ignore[type-arg]
    return next(change for change in payload["changes"] if change.get("intent", {}).get("name") == intent_name)


def test_initialize_returns_server_info() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})

    assert response is not None
    assert response["id"] == 1
    assert response["result"]["serverInfo"]["name"] == "befree-bubble-mcp"


def test_tools_list_includes_profile_list() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert response is not None
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert "bubble_profile_list" in names


def test_health_tool_returns_text_content() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "bubble_health_check", "arguments": {}},
        }
    )

    assert response is not None
    text = response["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert payload["ok"] is True
    assert payload["capabilities"]["mutations"] is True


def test_plan_tool_returns_valid_plan() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "bubble_plan",
                "arguments": {"message": "Create a text saying Hello"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["tool_name"] == "create_text"


def test_create_from_html_catalog_tool_uses_aria_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "engine": "aria_runtime", "write_count": 1, "executed": kwargs["execute"]}

    monkeypatch.setattr("bubble_mcp.server.tools.create_from_html_runtime", fake_create_from_html_runtime)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "create_from_html",
                "arguments": {
                    "profile": "smoke",
                    "app_id": "synthetic-app",
                    "context": "index",
                    "parent": "root",
                    "url": "https://example.com/page.html",
                    "execute": True,
                    "selector": "#home-area",
                    "translate_to_existing_styles": True,
                    "refresh_context": True,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["engine"] == "aria_runtime"
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["context"] == "index"
    assert calls[0]["parent"] == "root"
    assert calls[0]["html_file"] == "https://example.com/page.html"
    assert calls[0]["execute"] is True
    assert calls[0]["selector"] == "#home-area"
    assert calls[0]["translate_to_existing_styles"] is True
    assert calls[0]["refresh_context"] is True


def test_tools_list_includes_mutating_write_tool() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})

    assert response is not None
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert "bubble_editor_write" in names


def test_tools_list_exposes_only_advanced_html_importer() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 12, "method": "tools/list"})

    assert response is not None
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "create_from_html" in names
    assert "bubble_import_html" not in names
    assert "bubble_import_html_dry_run" not in names
    create_schema = next(tool for tool in tools if tool["name"] == "create_from_html")
    assert "rendered DOM" in create_schema["description"]


def test_tools_list_exposes_agent_usable_catalog_metadata() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 13, "method": "tools/list"})

    assert response is not None
    tools = response["result"]["tools"]
    assert tools
    for tool in tools:
        assert len(tool.get("description", "")) >= 80
        assert tool.get("inputSchema", {}).get("$schema") == "http://json-schema.org/draft-07/schema#"
        assert set(tool.get("annotations", {})) == {
            "readOnlyHint",
            "destructiveHint",
            "idempotentHint",
            "openWorldHint",
        }
        properties = tool.get("inputSchema", {}).get("properties", {})
        for property_schema in properties.values():
            assert property_schema.get("description")


def test_legacy_catalog_tools_expose_common_agent_arguments() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 14, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    schema = tools["create_group"]["inputSchema"]
    assert schema["additionalProperties"] is True
    for field in ["profile", "dry_run", "settings_path", "context", "parent", "execute", "app_id", "context_file"]:
        assert field in schema["properties"]
        assert schema["properties"][field]["description"]
    assert "name" in schema["properties"]
    assert "layout" in schema["properties"]
    assert "row_gap" in schema["properties"]
    assert "Create a Bubble group visual element" in tools["create_group"]["description"]
    assert tools["delete_group"]["annotations"]["destructiveHint"] is True
    assert tools["list_styles"]["annotations"]["readOnlyHint"] is True


def test_legacy_catalog_tools_expose_specific_family_schemas() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 15, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}

    create_page = tools["create_page"]["inputSchema"]
    assert create_page["required"] == ["profile", "name"]
    for field in ["layout", "meta_title", "gradient_angle", "app_id", "execute"]:
        assert field in create_page["properties"]

    create_style = tools["create_style"]["inputSchema"]
    assert create_style["required"] == ["profile", "name", "element_type"]
    for field in ["map_type", "custom_style", "border_radius"]:
        assert field in create_style["properties"]

    create_event = tools["create_event"]["inputSchema"]
    assert create_event["required"] == ["profile", "context", "event_type"]
    for field in ["only_when_json", "interval_seconds", "element_ref", "event_key"]:
        assert field in create_event["properties"]

    add_action = tools["add_action"]["inputSchema"]
    assert add_action["required"] == ["profile", "context", "action_type"]
    for field in ["fields", "thing", "to_email", "query_json"]:
        assert field in add_action["properties"]

    list_styles = tools["list_styles"]["inputSchema"]
    assert "execute" not in list_styles["properties"]
    assert "payload" not in list_styles["properties"]


def test_editor_write_records_mutation_overlay(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_session(
        "smoke",
        BubbleSessionData(
            app_id="synthetic-app",
            url="https://bubble.io/page?id=synthetic-app",
            method="POST",
            headers={"cookie": "sid=secret"},
            cookies="sid=secret",
            app_version="test",
            captured_at="2026-07-02T00:00:00+00:00",
            source="test",
        ),
    )

    payload = {
        "appname": "synthetic-app",
        "app_version": "test",
        "appVersion": "test",
        "changes": [
            {
                "intent": {"name": "CreatePage"},
                "path_array": ["%p3", "mcp01"],
                "body": {"id": "mcp01", "%nm": "mcp-01"},
            }
        ],
    }

    def fake_write(self, write_payload, session, *, dry_run=False):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "dry_run": dry_run,
            "response": {"last_change": "1"},
            "request": {"payload": write_payload},
        }

    monkeypatch.setattr("bubble_mcp.server.tools.BubbleEditorClient.write", fake_write)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "bubble_editor_write",
                "arguments": {"profile": "smoke", "execute": True, "payload": payload},
            },
        }
    )

    assert response is not None
    result = json.loads(response["result"]["content"][0]["text"])
    assert result["ok"] is True

    overlay_path = tmp_path / "contexts" / "smoke" / "synthetic-app-mutation-overlay.json"
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    assert overlay["entries"][0]["source"] == "bubble_editor_write"
    assert overlay["entries"][0]["changes"][0]["path_array"] == ["%p3", "mcp01"]


def test_tools_list_includes_full_aria_catalog() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})

    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert len(ARIA_BUBBLE_TOOL_NAMES) == 196
    assert set(ARIA_BUBBLE_TOOL_NAMES).issubset(names)


def test_direct_catalog_tool_call_compiles_when_supported() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "create_text",
                "arguments": {
                    "app_id": "synthetic-app",
                    "context": "index",
                    "content": "Hello",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["compiled"] is True
    assert first_change(payload["plan"]["steps"][0]["args"]["write_payload"], "CreateElement")["body"]["%x"] == "Text"


def test_compile_plan_tool_returns_write_payload() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "bubble_compile_plan",
                "arguments": {
                    "app_id": "synthetic-app",
                    "plan": {
                        "steps": [
                            {
                                "id": "s1",
                                "tool_name": "create_text",
                                "args": {"context": "index", "content": "Hello"},
                            }
                        ]
                    },
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert first_change(payload["plan"]["steps"][0]["args"]["write_payload"], "CreateElement")["body"]["%x"] == "Text"
