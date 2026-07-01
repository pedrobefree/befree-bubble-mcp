import json

from bubble_mcp.server.stdio import handle_request


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
    assert payload["capabilities"]["mutations"] is False


def test_plan_tool_returns_valid_dry_run_plan() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "bubble_plan_dry_run",
                "arguments": {"message": "Create a text saying Hello"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["tool_name"] == "create_text"
