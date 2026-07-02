import json

from bubble_mcp.server.stdio import handle_request
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES


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


def test_import_html_tool_can_compile_to_write_payloads() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "bubble_import_html",
                "arguments": {
                    "html": "<section><h1>Welcome</h1></section>",
                    "compile": True,
                    "app_id": "synthetic-app",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["validation"]["ok"] is True
    assert first_change(payload["plan"]["steps"][0]["args"]["write_payload"], "CreateElement")["body"]["%x"] == "Group"


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
                    "html": "<section><h1>Welcome</h1></section>",
                    "execute": True,
                    "selector": "section",
                    "translate_to_existing_styles": True,
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
    assert calls[0]["html"] == "<section><h1>Welcome</h1></section>"
    assert calls[0]["execute"] is True
    assert calls[0]["selector"] == "section"
    assert calls[0]["translate_to_existing_styles"] is True


def test_tools_list_includes_mutating_write_tool() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})

    assert response is not None
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert "bubble_editor_write" in names


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
