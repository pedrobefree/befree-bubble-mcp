import json
from types import SimpleNamespace

from bubble_mcp.runtime_coverage import catalog_coverage_report
import bubble_mcp.server.completion as completion_module
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
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
    assert "bubble_profile_status" in response["result"]["instructions"]
    assert "execute=false" in response["result"]["instructions"]
    assert response["result"]["capabilities"] == {
        "tools": {},
        "resources": {"templates": True},
        "prompts": {},
        "completions": {},
    }


def test_tools_list_includes_profile_list() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    names = list(tools)
    assert "bubble_profile_list" in names
    assert "bubble_profile_status" in names
    assert tools["bubble_session_list"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_session_list"]["annotations"]["destructiveHint"] is False


def test_ping_returns_empty_success() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 41, "method": "ping"})

    assert response == {"jsonrpc": "2.0", "id": 41, "result": {}}


def test_resources_list_and_read_agent_runtime() -> None:
    listed = handle_request({"jsonrpc": "2.0", "id": 30, "method": "resources/list"})

    assert listed is not None
    resources = listed["result"]["resources"]
    uris = [resource["uri"] for resource in resources]
    assert "bubble://docs/agent-quickstart" in uris
    assert "bubble://docs/agent-runtime" in uris
    assert "bubble://catalog/summary" in uris

    read = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "resources/read",
            "params": {"uri": "bubble://docs/agent-runtime"},
        }
    )

    assert read is not None
    content = read["result"]["contents"][0]
    assert content["mimeType"] == "text/markdown"
    assert "bubble_task_recipe" in content["text"]
    assert "Preview first" in content["text"]


def test_resources_read_agent_quickstart() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "resources/read",
            "params": {"uri": "bubble://docs/agent-quickstart"},
        }
    )

    assert response is not None
    content = response["result"]["contents"][0]
    assert content["mimeType"] == "text/markdown"
    assert "Default call sequence" in content["text"]
    assert "bubble_agent_guide" in content["text"]
    assert "Do not inspect repository code" in content["text"]


def test_resources_read_catalog_summary_json() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "resources/read",
            "params": {"uri": "bubble://catalog/summary"},
        }
    )

    assert response is not None
    content = response["result"]["contents"][0]
    assert content["mimeType"] == "application/json"
    payload = json.loads(content["text"])
    assert payload["ok"] is True
    assert payload["tool_count"] >= 220
    assert "bubble_profile_status" in payload["native_agent_tools"]
    assert "bubble_readiness_check" in payload["native_agent_tools"]
    assert "bubble_task_recipe" in payload["native_agent_tools"]
    assert "bubble_catalog_quality" in payload["native_agent_tools"]


def test_resource_templates_list_and_read_recipe_detail() -> None:
    listed = handle_request({"jsonrpc": "2.0", "id": 35, "method": "resources/templates/list"})

    assert listed is not None
    templates = listed["result"]["resourceTemplates"]
    assert templates[0]["uriTemplate"] == "bubble://recipes/{recipe_id}"
    assert any(template["uriTemplate"] == "bubble://profiles/{profile}/status" for template in templates)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 36,
            "method": "resources/read",
            "params": {"uri": "bubble://recipes/html_import"},
        }
    )

    assert response is not None
    content = response["result"]["contents"][0]
    assert content["mimeType"] == "application/json"
    payload = json.loads(content["text"])
    assert payload["ok"] is True
    assert payload["id"] == "html_import"
    assert payload["steps"][1]["tool"] == "create_from_html"


def test_profile_status_tool_and_resource(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={"client": BubbleProfile(name="client", app_id="client-app", appname="client-app")},
        )
    )

    tool_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {"name": "bubble_profile_status", "arguments": {"profile": "client"}},
        }
    )

    assert tool_response is not None
    tool_payload = json.loads(tool_response["result"]["content"][0]["text"])
    assert tool_payload["ok"] is True
    assert tool_payload["profile"]["app_id"] == "client-app"
    assert tool_response["result"]["structuredContent"] == tool_payload

    resource_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "resources/read",
            "params": {"uri": "bubble://profiles/client/status"},
        }
    )

    assert resource_response is not None
    content = resource_response["result"]["contents"][0]
    assert content["mimeType"] == "application/json"
    resource_payload = json.loads(content["text"])
    assert resource_payload["profile"]["name"] == "client"
    assert resource_payload["ready"] is False


def test_completion_suggests_recipe_ids() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 39,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/resource", "uri": "bubble://recipes/{recipe_id}"},
                "argument": {"name": "recipe_id", "value": "html"},
            },
        }
    )

    assert response is not None
    completion = response["result"]["completion"]
    assert "html_import" in completion["values"]
    assert completion["total"] >= 1
    assert completion["hasMore"] is False


def test_completion_suggests_profile_status_profile_ids(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={"client": BubbleProfile(name="client", app_id="client-app", appname="client-app")},
        )
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/resource", "uri": "bubble://profiles/{profile}/status"},
                "argument": {"name": "profile", "value": "cl"},
            },
        }
    )

    assert response is not None
    assert response["result"]["completion"]["values"] == ["client"]


def test_completion_suggests_prompt_profiles(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        completion_module,
        "load_settings",
        lambda: SimpleNamespace(profiles={"smoke": object(), "cliente2": object()}),
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 40,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/prompt", "name": "bubble-task-runbook"},
                "argument": {"name": "profile", "value": "s"},
            },
        }
    )

    assert response is not None
    assert response["result"]["completion"]["values"] == ["smoke"]


def test_completion_suggests_tool_arguments(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        completion_module,
        "load_settings",
        lambda: SimpleNamespace(profiles={"smoke": object(), "cliente2": object()}),
    )

    suite_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 47,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/tool", "name": "bubble_runtime_smoke"},
                "argument": {"name": "suite", "value": "agent"},
            },
        }
    )
    recipe_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 48,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/tool", "name": "bubble_task_recipe"},
                "argument": {"name": "recipe", "value": "html"},
            },
        }
    )
    profile_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 49,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/tool", "name": "create_page"},
                "argument": {"name": "profile", "value": "c"},
            },
        }
    )

    assert suite_response is not None
    assert recipe_response is not None
    assert profile_response is not None
    assert suite_response["result"]["completion"]["values"] == ["agent-routing"]
    assert recipe_response["result"]["completion"]["values"] == ["html_import"]
    assert profile_response["result"]["completion"]["values"] == ["cliente2"]


def test_prompts_list_and_get_task_runbook() -> None:
    listed = handle_request({"jsonrpc": "2.0", "id": 33, "method": "prompts/list"})

    assert listed is not None
    names = [prompt["name"] for prompt in listed["result"]["prompts"]]
    assert "bubble-task-runbook" in names
    assert "bubble-html-import" in names

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 34,
            "method": "prompts/get",
            "params": {
                "name": "bubble-task-runbook",
                "arguments": {"task": "Create a page", "profile": "smoke", "context": "index"},
            },
        }
    )

    assert response is not None
    message = response["result"]["messages"][0]
    assert message["role"] == "user"
    assert "bubble_profile_status" in message["content"]["text"]
    assert message["content"]["text"].index("bubble_profile_status") < message["content"]["text"].index(
        "bubble_task_recipe"
    )
    assert "bubble_task_recipe" in message["content"]["text"]
    assert "Create a page" in message["content"]["text"]
    assert "Do not inspect repository code" in message["content"]["text"]


def test_prompt_get_html_import_prioritizes_profile_status() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 46,
            "method": "prompts/get",
            "params": {
                "name": "bubble-html-import",
                "arguments": {
                    "profile": "smoke",
                    "context": "mcp-01",
                    "url": "https://example.com",
                    "selector": "#home-area",
                },
            },
        }
    )

    assert response is not None
    text = response["result"]["messages"][0]["content"]["text"]
    assert "bubble_profile_status" in text
    assert "bubble_task_recipe" in text
    assert text.index("bubble_profile_status") < text.index("bubble_task_recipe")
    assert "create_from_html" in text


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
    assert payload["capabilities"]["aria_runtime_dispatch"] is True


def test_tool_call_returns_structured_content_matching_redacted_text() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 37,
            "method": "tools/call",
            "params": {"name": "bubble_health_check", "arguments": {}},
        }
    )

    assert response is not None
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    assert result["structuredContent"] == payload
    assert result["structuredContent"]["ok"] is True


def test_tool_call_errors_are_tool_results_not_protocol_errors() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 38,
            "method": "tools/call",
            "params": {"name": "bubble_context_detect", "arguments": {}},
        }
    )

    assert response is not None
    assert "error" not in response
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    assert result["isError"] is True
    assert result["structuredContent"] == payload
    assert payload["ok"] is False
    assert payload["tool"] == "bubble_context_detect"
    assert "requires a profile" in payload["error"]


def test_tool_coverage_reports_no_uncovered_aria_catalog_tools() -> None:
    report = catalog_coverage_report()

    assert report["ok"] is True
    assert report["aria_catalog"]["count"] == len(ARIA_BUBBLE_TOOL_NAMES)
    assert report["aria_catalog"]["uncovered_count"] == 0
    assert report["aria_catalog"]["uncovered"] == []
    assert report["uncovered_count"] == 0
    assert report["uncovered"] == []
    assert "tools" not in report
    assert report["by_coverage"]["runtime_direct"] >= 180
    assert report["by_coverage"]["runtime_alias"] >= 10

    detailed = catalog_coverage_report(include_tools=True)
    assert len(detailed["tools"]) == detailed["tool_count"]


def test_tool_coverage_tool_is_exposed() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": "bubble_tool_coverage", "arguments": {}},
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["aria_catalog"]["uncovered_count"] == 0
    assert "tools" not in payload

    detailed_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {"name": "bubble_tool_coverage", "arguments": {"include_details": True}},
        }
    )

    assert detailed_response is not None
    detailed_payload = json.loads(detailed_response["result"]["content"][0]["text"])
    assert len(detailed_payload["tools"]) == detailed_payload["tool_count"]


def test_catalog_quality_tool_is_exposed() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {"name": "bubble_catalog_quality", "arguments": {}},
        }
    )

    assert response is not None
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["summary"]["issue_count"] == 0
    assert result["structuredContent"] == payload


def test_readiness_tool_is_exposed() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "tools/call",
            "params": {"name": "bubble_readiness_check", "arguments": {}},
        }
    )

    assert response is not None
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["summary"] == {"checks": 3, "passed": 3, "failed": 0}
    assert [check["name"] for check in payload["checks"]] == [
        "health",
        "catalog_gate",
        "agent_routing",
    ]
    assert result["structuredContent"] == payload


def test_agent_guide_routes_user_tasks_without_cli_discovery() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 25,
            "method": "tools/call",
            "params": {
                "name": "bubble_agent_guide",
                "arguments": {
                    "task": "Convert #home-area from a URL into page mcp-01, then inspect changelog for the branch."
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["direct_tool_policy"]["use_mcp_tools_directly"] is True
    assert payload["direct_tool_policy"]["avoid_shell_cli_discovery"] is True
    intents = {route["intent"] for route in payload["recommended_routes"]}
    assert "import_html_component" in intents
    assert "branches_or_changelog" in intents
    html_route = next(route for route in payload["recommended_routes"] if route["intent"] == "import_html_component")
    assert html_route["tools"] == ["create_from_html"]


def test_tool_search_returns_compact_relevant_catalog_matches() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 26,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_search",
                "arguments": {"query": "html selector import", "limit": 5},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["limit"] == 5
    assert payload["matches"]
    names = [match["name"] for match in payload["matches"]]
    assert "create_from_html" in names
    create_from_html = next(match for match in payload["matches"] if match["name"] == "create_from_html")
    assert create_from_html["required"] == ["profile", "context", "parent"]
    assert "selector" in create_from_html["properties"]
    assert create_from_html["annotations"]["readOnlyHint"] is False


def test_task_recipe_returns_ordered_html_import_steps() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 27,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_recipe",
                "arguments": {
                    "task": "Convert #home-area from a URL into page mcp-01",
                    "profile": "smoke",
                    "context": "mcp-01",
                    "parent": "root",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["recipe"] == "html_import"
    assert payload["inputs"]["profile"] == "smoke"
    assert payload["inputs"]["context"] == "mcp-01"
    assert payload["matched"]["tools"] == ["create_from_html", "bubble_context_detect"]
    tools = [step["tool"] for step in payload["steps"]]
    assert tools == ["bubble_context_detect", "create_from_html", "create_from_html"]
    assert payload["steps"][1]["args"]["execute"] is False


def test_task_recipe_quality_gate_uses_consolidated_coverage_smoke() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 50,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_recipe",
                "arguments": {
                    "task": "validate MCP catalog coverage and quality",
                    "profile": "cliente2",
                    "context": "index",
                    "parent": "root",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["recipe"] == "quality_gate"
    assert payload["matched"]["tools"] == [
        "bubble_readiness_check",
        "bubble_runtime_smoke",
        "bubble_health_check",
        "bubble_tool_coverage",
        "bubble_catalog_quality",
    ]
    assert payload["steps"][0]["tool"] == "bubble_readiness_check"
    assert payload["inputs"]["profile"] == "cliente2"
    assert payload["steps"][0]["args"]["profile"] == "$profile"
    assert payload["steps"][1]["tool"] == "bubble_runtime_smoke"
    assert payload["steps"][1]["args"]["suite"] == "family-preview"


def test_agent_routing_understands_portuguese_page_creation() -> None:
    guide_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {
                "name": "bubble_agent_guide",
                "arguments": {"task": "crie uma nova página chamada mcp-02 no profile smoke"},
            },
        }
    )
    recipe_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_recipe",
                "arguments": {"task": "crie uma nova página chamada mcp-02 no profile smoke"},
            },
        }
    )
    search_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "tools/call",
            "params": {"name": "bubble_tool_search", "arguments": {"query": "criar página", "limit": 5}},
        }
    )

    assert guide_response is not None
    assert recipe_response is not None
    assert search_response is not None
    guide = json.loads(guide_response["result"]["content"][0]["text"])
    recipe = json.loads(recipe_response["result"]["content"][0]["text"])
    search = json.loads(search_response["result"]["content"][0]["text"])
    route_intents = {route["intent"] for route in guide["recommended_routes"]}
    assert "manage_pages_or_reusables" in route_intents
    assert "check_server_or_catalog" not in route_intents
    assert recipe["recipe"] == "page_or_reusable"
    assert "create_page" in [match["name"] for match in search["matches"]]


def test_runtime_smoke_tool_runs_coverage_suite() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {"name": "bubble_runtime_smoke", "arguments": {"suite": "coverage"}},
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["summary"]["failed"] == 0
    assert [result["tool"] for result in payload["results"]] == [
        "bubble_tool_coverage",
        "bubble_catalog_quality",
    ]


def test_runtime_smoke_tool_runs_agent_routing_suite() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 46,
            "method": "tools/call",
            "params": {"name": "bubble_runtime_smoke", "arguments": {"suite": "agent-routing"}},
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["suite"] == "agent-routing"
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["passed"] == 6


def test_runtime_smoke_tool_requires_execute_for_execute_write() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {"name": "bubble_runtime_smoke", "arguments": {"suite": "execute-write", "profile": "cliente2"}},
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert payload["error"] == "execute-write requires execute=true."


def test_runtime_smoke_schema_exposes_execute_write_controls() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 24, "method": "tools/list"})

    assert response is not None
    tools = response["result"]["tools"]
    smoke = next(tool for tool in tools if tool["name"] == "bubble_runtime_smoke")
    guide = next(tool for tool in tools if tool["name"] == "bubble_agent_guide")
    search = next(tool for tool in tools if tool["name"] == "bubble_tool_search")
    recipe = next(tool for tool in tools if tool["name"] == "bubble_task_recipe")
    assert guide["annotations"]["readOnlyHint"] is True
    assert guide["annotations"]["idempotentHint"] is True
    assert "task" in guide["inputSchema"]["properties"]
    assert search["annotations"]["readOnlyHint"] is True
    assert search["annotations"]["idempotentHint"] is True
    assert search["inputSchema"]["required"] == ["query"]
    assert recipe["annotations"]["readOnlyHint"] is True
    assert recipe["annotations"]["idempotentHint"] is True
    assert recipe["inputSchema"]["required"] == ["task"]
    assert "recipe" in recipe["inputSchema"]["properties"]
    properties = smoke["inputSchema"]["properties"]
    assert "execute-write" in properties["suite"]["enum"]
    assert "family-preview" in properties["suite"]["enum"]
    assert "execute" in properties
    assert "cleanup" in properties
    assert "run_id" in properties
    assert "verify_context" in properties
    assert "verification_output" in properties


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
    assert payload["structural_validation"]["status"] == "previewable"
    assert payload["next_user_action"] == "review_preview_or_execute"


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


def test_legacy_catalog_tool_dispatches_to_aria_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    class FakePayloadBuilder:
        send_to_webhook = None
        to_json = None

        def __init__(self, appname="synthetic-app"):  # type: ignore[no-untyped-def]
            self.appname = appname

        def build(self):  # type: ignore[no-untyped-def]
            return {
                "v": 1,
                "appname": self.appname,
                "changes": [
                    {
                        "intent": {"name": "CreateElement"},
                        "path_array": ["%p3", "bPage"],
                        "body": {"%x": "Page", "%p": {"%nm": "mcp-03"}, "id": "bPage"},
                    }
                ],
            }

        def _to_json_impl(self):  # type: ignore[no-untyped-def]
            return json.dumps(self.build())

    class FakeBubbleSdk:
        PayloadBuilder = FakePayloadBuilder

    class FakeBubbleCliModule:
        inquirer = None

        class BubbleCLI:
            def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                calls.append(("init", kwargs))
                self.appname = kwargs["appname"]

            def create_page(self, name, dry_run=False, **kwargs):  # type: ignore[no-untyped-def]
                calls.append(("create_page", {"name": name, "dry_run": dry_run, **kwargs}))
                payload_builder = FakePayloadBuilder(appname=self.appname)
                if dry_run:
                    return payload_builder.to_json()
                return payload_builder.send_to_webhook("local://bubble-mcp")

    FakePayloadBuilder.to_json = FakePayloadBuilder._to_json_impl

    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch._load_aria_runtime_modules",
        lambda: (FakeBubbleCliModule, FakeBubbleSdk),
    )
    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch._resolve_runtime_environment",
        lambda args: __import__("bubble_mcp.aria_dispatch").aria_dispatch.AriaRuntimeEnvironment(
            profile=args["profile"],
            app_id=args["app_id"],
            app_version="test",
            app_json_path="/tmp/app.bubble",
            consolelog_json_path=None,
            crawler_index_path=None,
            mutation_overlay_path=None,
        ),
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "create_page",
                "arguments": {
                    "profile": "smoke",
                    "app_id": "synthetic-app",
                    "name": "mcp-03",
                    "execute": False,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["engine"] == "aria_runtime"
    assert payload["compiled"] is True
    assert payload["executed"] is False
    assert payload["write_count"] == 1
    assert payload["results"][0]["payload"]["changes"][0]["body"]["%x"] == "Page"
    assert calls[0][0] == "init"
    assert calls[1] == ("create_page", {"name": "mcp-03", "dry_run": True})


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


def test_native_family_schemas_expose_agent_selection_constraints() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 19, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}

    context_detect = tools["bubble_context_detect"]["inputSchema"]
    assert context_detect["properties"]["app_version"]["default"] == "test"
    assert context_detect["properties"]["force"]["default"] is False
    assert ".bubble export" in context_detect["properties"]["bubble_file"]["description"]

    html_import = tools["create_from_html"]["inputSchema"]
    assert html_import["required"] == ["profile", "context", "parent"]
    assert html_import["anyOf"] == [
        {"required": ["url"]},
        {"required": ["html_file"]},
        {"required": ["file"]},
        {"required": ["html"]},
    ]
    assert html_import["properties"]["url"]["format"] == "uri"
    assert html_import["properties"]["rendered_html"]["default"] is True
    assert html_import["properties"]["style_match_threshold"]["minimum"] == 0
    assert html_import["properties"]["style_match_threshold"]["maximum"] == 1

    session_import = tools["bubble_session_import"]["inputSchema"]
    assert session_import["properties"]["session"]["properties"]["headers"]["type"] == "object"
    assert session_import["properties"]["session"]["properties"]["url"]["format"] == "uri"

    changelog = tools["bubble_changelog_fetch"]["inputSchema"]
    assert changelog["properties"]["start_index"]["minimum"] == 0
    assert changelog["properties"]["num_fetch"]["minimum"] == 1
    assert changelog["properties"]["num_fetch"]["maximum"] == 200
    assert "Element" in changelog["properties"]["change_type"]["examples"]

    expert_export = tools["bubble_eval_export_expert"]["inputSchema"]
    assert expert_export["required"] == ["input", "output"]
    assert expert_export["properties"]["input"]["description"]
    assert expert_export["properties"]["output"]["description"]


def test_native_mutating_schemas_make_execution_and_confirmation_explicit() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 20, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}

    for name in [
        "create_from_html",
        "bubble_editor_write",
        "bubble_execute_plan",
        "bubble_branch_create",
        "bubble_branch_delete",
    ]:
        execute_schema = tools[name]["inputSchema"]["properties"]["execute"]
        assert execute_schema["type"] == "boolean"
        assert execute_schema["default"] is False
        assert "apply the change in Bubble" in execute_schema["description"]

    branch_create = tools["bubble_branch_create"]["inputSchema"]
    assert "sub-branch" in branch_create["properties"]["from_app_version"]["description"]
    assert branch_create["properties"]["version_control_api_version"]["default"] == 7

    branch_delete = tools["bubble_branch_delete"]["inputSchema"]
    assert branch_delete["properties"]["soft_delete"]["default"] is True
    assert branch_delete["properties"]["confirm"]["default"] is False
    assert "destructive" in branch_delete["properties"]["confirm"]["description"]
    assert tools["bubble_branch_delete"]["annotations"]["destructiveHint"] is True


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


def test_tools_list_exposes_branch_and_changelog_tools() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 16, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    for name in [
        "bubble_branch_list",
        "bubble_branch_contributors",
        "bubble_changelog_fetch",
        "bubble_branch_create",
        "bubble_branch_delete",
    ]:
        assert name in tools
        assert tools[name]["inputSchema"]["properties"]["profile"]["description"]

    assert tools["bubble_branch_list"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_branch_contributors"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_changelog_fetch"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_eval_export_expert"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_branch_create"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_branch_create"]["annotations"]["openWorldHint"] is True
    assert tools["bubble_branch_delete"]["annotations"]["destructiveHint"] is True
    assert tools["bubble_branch_delete"]["inputSchema"]["required"] == ["profile", "app_version"]
    assert "from_app_version" in tools["bubble_branch_create"]["inputSchema"]["properties"]
    assert "change_type" in tools["bubble_changelog_fetch"]["inputSchema"]["properties"]


def test_changelog_tool_maps_flat_filters(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_fetch_changelog_entries(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "entries": []}

    monkeypatch.setattr("bubble_mcp.server.tools.fetch_changelog_entries", fake_fetch_changelog_entries)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 17,
            "method": "tools/call",
            "params": {
                "name": "bubble_changelog_fetch",
                "arguments": {
                    "profile": "smoke",
                    "start_index": 10,
                    "num_fetch": 25,
                    "change_type": "Workflow",
                    "root": "bRoot",
                    "user_id": "u1,u2",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["start_index"] == 10
    assert calls[0]["num_fetch"] == 25
    assert calls[0]["filters"] == {"type": "Workflow", "root": "bRoot", "user_id": ["u1", "u2"]}


def test_branch_create_tool_routes_sub_branch_source(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_bubble_branch(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "request": {"payload": kwargs}}

    monkeypatch.setattr("bubble_mcp.server.tools.create_bubble_branch", fake_create_bubble_branch)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 18,
            "method": "tools/call",
            "params": {
                "name": "bubble_branch_create",
                "arguments": {
                    "profile": "smoke",
                    "name": "sub-feature",
                    "from_app_version": "parent-branch-id",
                    "description": "child branch",
                    "execute": True,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert calls[0]["from_app_version"] == "parent-branch-id"
    assert calls[0]["execute"] is True


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
