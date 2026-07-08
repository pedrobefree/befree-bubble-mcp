import json
from types import SimpleNamespace

from bubble_mcp.runtime_coverage import catalog_coverage_report
import bubble_mcp.server.completion as completion_module
import bubble_mcp.server.tools as tools_module
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.server.stdio import handle_request
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.sessions.store import BubbleSessionData, load_session, save_session, session_from_payload


def first_change(payload: dict, intent_name: str) -> dict:  # type: ignore[type-arg]
    return next(change for change in payload["changes"] if change.get("intent", {}).get("name") == intent_name)


def test_initialize_returns_server_info() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})

    assert response is not None
    assert response["id"] == 1
    assert response["result"]["serverInfo"]["name"] == "befree-bubble-mcp"
    assert "bubble_task_runbook" in response["result"]["instructions"]
    assert "bubble_project_bootstrap" in response["result"]["instructions"]
    assert "bubble_session_login" in response["result"]["instructions"]
    assert "bubble_agent_guide or" not in response["result"]["instructions"]
    assert "execute=false" in response["result"]["instructions"]
    assert "bubble_context_find" in response["result"]["instructions"]
    assert "include_metadata=false" in response["result"]["instructions"]
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
    assert "bubble_project_bootstrap" in names
    assert "bubble_profile_add" in names
    assert "bubble_profile_list" in names
    assert "bubble_profile_status" in names
    assert "bubble_profile_cache_refresh" in names
    assert "bubble_session_inspect" in names
    assert "bubble_session_login" in names
    assert "bubble_visual_compare" in names
    assert "bubble_visual_audit" in names
    assert "bubble_visual_capture" in names
    assert "bubble_visual_capture_actual" in names
    assert "bubble_performance_audit" in names
    assert "bubble_workload_usage_by_date" in names
    assert "bubble_workload_usage_breakdown" in names
    assert "bubble_logs_fetch" in names
    assert "bubble_workflow_runs_get" in names
    assert "bubble_task_runbook" in names
    assert "batch" in names
    assert tools["bubble_project_bootstrap"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_project_bootstrap"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_project_bootstrap"]["inputSchema"]["required"] == ["profile"]
    assert tools["bubble_profile_add"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_profile_add"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_profile_add"]["inputSchema"]["required"] == ["name", "app_id"]
    assert tools["bubble_profile_cache_refresh"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_profile_cache_refresh"]["inputSchema"]["required"] == ["profile"]
    assert tools["bubble_profile_cache_refresh"]["inputSchema"]["properties"]["force"]["default"] is True
    assert tools["batch"]["inputSchema"]["required"] == ["profile", "commands"]
    assert "commands" in tools["batch"]["description"].lower()
    assert "temporary files" in tools["batch"]["description"].lower()
    assert tools["bubble_session_list"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_session_list"]["annotations"]["destructiveHint"] is False
    assert tools["bubble_session_inspect"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_session_inspect"]["inputSchema"]["required"] == ["profile"]
    assert tools["bubble_session_login"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_session_login"]["annotations"]["openWorldHint"] is True
    assert tools["bubble_session_login"]["inputSchema"]["required"] == ["profile"]
    assert tools["bubble_visual_compare"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_visual_compare"]["inputSchema"]["required"] == ["reference", "actual"]
    assert tools["bubble_visual_audit"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_visual_audit"]["annotations"]["openWorldHint"] is True
    assert "anyOf" in tools["bubble_visual_audit"]["inputSchema"]
    assert tools["bubble_visual_capture"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_visual_capture"]["annotations"]["openWorldHint"] is True
    assert tools["bubble_visual_capture"]["inputSchema"]["required"] == ["source"]
    assert tools["bubble_visual_capture_actual"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_visual_capture_actual"]["annotations"]["openWorldHint"] is True
    assert tools["bubble_performance_audit"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_performance_audit"]["inputSchema"]["required"] == ["profile"]
    assert tools["bubble_logs_fetch"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_logs_fetch"]["inputSchema"]["properties"]["app_version"]["default"] == "live"
    assert "Defaults app_version to live" in tools["bubble_logs_fetch"]["description"]
    assert tools["bubble_workload_usage_by_date"]["inputSchema"]["required"] == ["profile", "start", "end"]
    assert tools["bubble_workload_usage_breakdown"]["inputSchema"]["properties"]["granularity"]["enum"] == [
        "minute",
        "hour",
        "day",
    ]
    assert tools["create_group"]["inputSchema"]["properties"]["layout"]["enum"] == [
        "column",
        "row",
        "align_to_parent",
        "fixed",
    ]
    assert tools["create_input"]["inputSchema"]["properties"]["content_format"]["enum"] == [
        "text",
        "email",
        "password",
        "integer",
        "decimal",
        "date",
    ]
    assert "exact" in tools["bubble_context_find"]["inputSchema"]["properties"]
    assert "include_metadata" in tools["bubble_context_find"]["inputSchema"]["properties"]
    for transfer_tool in [
        "bubble_transfer_inventory",
        "bubble_transfer_plan",
        "bubble_transfer_preview",
        "bubble_transfer_execute",
        "bubble_transfer_status",
    ]:
        assert transfer_tool in tools
    assert tools["bubble_transfer_inventory"]["inputSchema"]["required"] == [
        "source_profile",
        "source_type",
        "source_ref",
    ]
    assert tools["bubble_transfer_plan"]["inputSchema"]["required"] == [
        "source_profile",
        "target_profile",
        "source_type",
        "source_ref",
    ]
    assert tools["bubble_transfer_plan"]["inputSchema"]["properties"]["reuse_policy"]["enum"] == [
        "prefer_existing",
        "exact_only",
        "create_new",
    ]
    assert tools["bubble_transfer_execute"]["inputSchema"]["required"] == ["transfer_id", "execute", "confirm"]


def test_profile_cache_refresh_tool_forces_context_detection(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls: list[dict] = []
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="cliente2",
            profiles={
                "cliente2": BubbleProfile(
                    name="cliente2",
                    app_id="courselaunch",
                    appname="courselaunch",
                    app_version="test",
                )
            },
        )
    )

    class FakeDetectionResult:
        ok = True
        app_id = "courselaunch"
        source = "downloaded_bubble"
        crawler_index_path = None

        def __init__(self) -> None:
            self.context_path = tmp_path / "contexts" / "cliente2" / "courselaunch-context.json"
            self.summary = {"app_id": "courselaunch"}

        def to_dict(self) -> dict:
            return {
                "ok": True,
                "app_id": "courselaunch",
                "source": "downloaded_bubble",
                "context_path": str(self.context_path),
                "crawler_index_path": None,
                "summary": self.summary,
                "attempts": [],
            }

    def fake_detect_project_context(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return FakeDetectionResult()

    monkeypatch.setattr(tools_module, "detect_project_context", fake_detect_project_context)
    monkeypatch.setattr(
        tools_module,
        "profile_status",
        lambda profile, max_age_hours=24: {"ok": True, "ready": False, "profile": {"name": profile}},
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 601,
            "method": "tools/call",
            "params": {
                "name": "bubble_profile_cache_refresh",
                "arguments": {"profile": "cliente2"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["profile"] == "cliente2"
    assert payload["force"] is True
    assert payload["source"] == "downloaded_bubble"
    assert payload["next_user_action"] == "Profile cache refreshed. Use bubble_profile_status only if you need readiness details."
    assert calls[0]["profile"] == "cliente2"
    assert calls[0]["app_id"] == "courselaunch"
    assert calls[0]["force"] is True


def test_transfer_inventory_tool_uses_source_profile_context(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "contexts" / "source" / "source-app-context.json"
    context_path.parent.mkdir(parents=True)
    context_path.write_text(
        json.dumps(
            {
                "app_id": "source-app",
                "source": "test",
                "nodes": [
                    {"id": "page:index", "label": "index", "type": "page", "metadata": {"bubble_id": "bPage"}},
                    {
                        "id": "element:bHero",
                        "label": "gp_Hero",
                        "type": "element",
                        "metadata": {"bubble_id": "bHero", "properties": {"%x": "Group", "%p": {"%nm": "gp_Hero"}}},
                    },
                ],
                "edges": [{"source": "page:index", "target": "element:bHero", "type": "contains"}],
            }
        ),
        encoding="utf-8",
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile=None,
            profiles={"source": BubbleProfile(name="source", app_id="source-app", appname="source-app")},
        )
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 802,
            "method": "tools/call",
            "params": {
                "name": "bubble_transfer_inventory",
                "arguments": {"source_profile": "source", "source_type": "element", "source_ref": "gp_Hero"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["source"]["profile"] == "source"
    assert payload["counts"]["nodes"] == 1
    assert "nodes" not in payload


def test_visual_compare_tool_returns_structured_report() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {
                "name": "bubble_visual_compare",
                "arguments": {
                    "reference": "tests/fixtures/visual-snapshots/hero-reference.json",
                    "actual": "tests/fixtures/visual-snapshots/hero-actual-ok.json",
                    "require_images": True,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["summary"]["comparisons"] > 0


def test_visual_audit_tool_returns_repair_plan() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 47,
            "method": "tools/call",
            "params": {
                "name": "bubble_visual_audit",
                "arguments": {
                    "reference": "tests/fixtures/visual-snapshots/hero-reference.json",
                    "actual": "tests/fixtures/visual-snapshots/hero-actual-bad.json",
                    "profile": "smoke",
                    "context": "mcp-01",
                    "parent": "gp_home",
                    "app_id": "demo-app",
                    "require_images": True,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert payload["summary"]["repairable_count"] > 0
    assert payload["repair_plan"]["executable"] is True
    assert any(step["tool_name"] == "update_image_element" for step in payload["repair_plan"]["plan"]["steps"])


def test_visual_capture_tool_returns_structured_snapshot() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "tools/call",
            "params": {
                "name": "bubble_visual_capture",
                "arguments": {
                    "source": "tests/fixtures/html/hero.html",
                    "selector": "#hero",
                    "rendered_html": False,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["root"]["id"] == "hero"
    assert payload["rendered"] is False


def test_visual_capture_actual_tool_resolves_bubble_preview(monkeypatch) -> None:
    calls = []

    def fake_capture(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "bubble": {"url": "https://demo.bubbleapps.io/version-test/mcp-01"},
            "root": {"id": "hero"},
            "nodes": [],
        }

    monkeypatch.setattr(tools_module, "capture_bubble_visual_snapshot", fake_capture)
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 46,
            "method": "tools/call",
            "params": {
                "name": "bubble_visual_capture_actual",
                "arguments": {
                    "app_id": "demo",
                    "app_version": "test",
                    "page": "mcp-01",
                    "selector": "#hero",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["bubble"]["url"] == "https://demo.bubbleapps.io/version-test/mcp-01"
    assert calls[0]["app_id"] == "demo"
    assert calls[0]["page"] == "mcp-01"


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
    assert "bubble_context_find" in content["text"]
    assert "include_metadata=false" in content["text"]


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
    assert "bubble_task_runbook" in content["text"]
    assert "Do not inspect repository code" in content["text"]
    assert "bubble://tools/{tool_name}" in content["text"]
    assert "exact=true" in content["text"]


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
    assert "bubble_project_bootstrap" in payload["native_agent_tools"]
    assert "bubble_profile_status" in payload["native_agent_tools"]
    assert "bubble_readiness_check" in payload["native_agent_tools"]
    assert "bubble_task_runbook" in payload["native_agent_tools"]
    assert "bubble_task_recipe" in payload["native_agent_tools"]
    assert "bubble_catalog_quality" in payload["native_agent_tools"]
    assert "bubble_context_find" in payload["native_agent_tools"]
    assert "bubble_context_detect" in payload["native_agent_tools"]
    assert "bubble://tools/{tool_name}" in payload["recommended_entrypoints"]


def test_resource_templates_list_and_read_recipe_detail() -> None:
    listed = handle_request({"jsonrpc": "2.0", "id": 35, "method": "resources/templates/list"})

    assert listed is not None
    templates = listed["result"]["resourceTemplates"]
    assert templates[0]["uriTemplate"] == "bubble://recipes/{recipe_id}"
    assert any(template["uriTemplate"] == "bubble://profiles/{profile}/status" for template in templates)
    assert any(template["uriTemplate"] == "bubble://tools/{tool_name}" for template in templates)

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
    assert payload["steps"][1]["tool"] == "bubble_context_find"
    assert payload["steps"][1]["args"]["exact"] is True
    assert payload["steps"][1]["args"]["include_metadata"] is False
    assert payload["steps"][2]["tool"] == "create_from_html"


def test_resource_templates_read_tool_schema_detail() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 37,
            "method": "resources/read",
            "params": {"uri": "bubble://tools/create_from_html"},
        }
    )

    assert response is not None
    content = response["result"]["contents"][0]
    assert content["mimeType"] == "application/json"
    payload = json.loads(content["text"])
    assert payload["ok"] is True
    assert payload["tool"]["name"] == "create_from_html"
    assert "profile" in payload["tool"]["inputSchema"]["properties"]
    assert "selector" in payload["tool"]["inputSchema"]["properties"]
    assert payload["tool"]["annotations"]["readOnlyHint"] is False


def test_profile_add_tool_writes_local_settings(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 38,
            "method": "tools/call",
            "params": {
                "name": "bubble_profile_add",
                "arguments": {
                    "name": "client",
                    "app_id": "client-app",
                    "appname": "client-appname",
                    "app_version": "test",
                    "editor_url": "https://bubble.io/page?id=client-app",
                    "app_json_path": "contexts/client/app.bubble",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["profile"] == "client"
    assert payload["app_id"] == "client-app"
    assert response["result"]["structuredContent"] == payload

    listed = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 39,
            "method": "tools/call",
            "params": {"name": "bubble_profile_list"},
        }
    )
    assert listed is not None
    list_payload = json.loads(listed["result"]["content"][0]["text"])
    assert list_payload["default_profile"] == "client"
    assert list_payload["profiles"][0]["name"] == "client"
    assert list_payload["profiles"][0]["app_id"] == "client-app"


def test_project_bootstrap_creates_profile_and_returns_next_actions(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 40,
            "method": "tools/call",
            "params": {
                "name": "bubble_project_bootstrap",
                "arguments": {
                    "profile": "client",
                    "app_id": "client-app",
                    "app_version": "test",
                    "editor_url": "https://bubble.io/page?id=client-app",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["profile"] == "client"
    assert payload["profile_changed"] is True
    assert payload["ready"] is False
    assert payload["status"]["profile"]["app_id"] == "client-app"
    assert [action["tool"] for action in payload["next_actions"]] == [
        "bubble_session_login",
        "bubble_context_detect",
    ]


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


def test_session_inspect_tool_returns_redacted_computed_headers(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_session(
        "client",
        BubbleSessionData(
            app_id="client-app",
            url="https://bubble.io/page?id=client-app",
            method="POST",
            headers={
                "accept": "application/json",
                "cookie": "bubble_session=secret-cookie",
                "user-agent": "Test Agent",
                "x-bubble-client-version": "client-version-token",
            },
            cookies="bubble_session=secret-cookie",
            app_version="test",
            captured_at="2026-07-04T10:00:00+00:00",
            source="test",
        ),
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "tools/call",
            "params": {"name": "bubble_session_inspect", "arguments": {"profile": "client"}},
        }
    )

    assert response is not None
    raw_text = response["result"]["content"][0]["text"]
    assert "secret-cookie" not in raw_text
    payload = json.loads(raw_text)
    assert payload["ok"] is True
    assert payload["profile"] == "client"
    assert payload["session"]["cookies"] == "[REDACTED]"
    assert payload["session_auth_present"] is True
    assert payload["session_auth_value_length"] == len("bubble_session=secret-cookie")
    assert "cookie" in [key.lower() for key in payload["stored_header_keys"]]
    assert "x-bubble-appname" in payload["computed_write_header_keys"]
    assert payload["computed_write_headers"]["cookie"] == "[REDACTED]"
    assert response["result"]["structuredContent"] == payload


def test_session_login_tool_saves_redacted_browser_session(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={"client": BubbleProfile(name="client", app_id="client-app", appname="client-app")},
        )
    )

    def fake_capture_session_with_playwright(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["app_id"] == "client-app"
        assert kwargs["wait_seconds"] == 5
        assert kwargs["user_data_dir"] == tmp_path / "browser-profiles" / "client"
        kwargs["progress"]("Session cookies detected. You can close the browser now.")
        return session_from_payload(
            {
                "appId": "client-app",
                "url": "https://bubble.io/page?id=client-app",
                "headers": {"Cookie": "sid=secret", "User-Agent": "test"},
                "appVersion": "test",
                "source": "browser",
            }
        )

    monkeypatch.setattr("bubble_mcp.server.tools.capture_session_with_playwright", fake_capture_session_with_playwright)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 47,
            "method": "tools/call",
            "params": {
                "name": "bubble_session_login",
                "arguments": {"profile": "client", "wait_seconds": 5},
            },
        }
    )

    assert response is not None
    raw_text = response["result"]["content"][0]["text"]
    assert "sid=secret" not in raw_text
    payload = json.loads(raw_text)
    assert payload["ok"] is True
    assert payload["profile"] == "client"
    assert payload["progress"] == ["Session cookies detected. You can close the browser now."]
    assert payload["session"]["headers"]["Cookie"] == "[REDACTED]"
    saved = load_session("client", tmp_path)
    assert saved is not None
    assert saved.cookies == "sid=secret"


def test_context_find_tool_returns_agent_summary_envelope() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 46,
            "method": "tools/call",
            "params": {
                "name": "bubble_context_find",
                "arguments": {
                    "file": "tests/fixtures/context/synthetic-app-context.json",
                    "query": "page:index",
                    "exact": True,
                    "include_metadata": False,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["query"] == "page:index"
    assert payload["count"] == 1
    assert payload["exact"] is True
    assert payload["include_metadata"] is False
    assert payload["results"][0]["match_field"] == "id"
    assert "metadata" not in payload["results"][0]
    assert response["result"]["structuredContent"] == payload


def test_context_find_tool_can_resolve_context_from_profile(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "client-context.json"
    context_path.write_text(
        '{"app_id":"synthetic-app","source":"test","nodes":[{"id":"page:index","label":"index","type":"page","metadata":{"bubble_id":"index"}}],"edges":[]}\n',
        encoding="utf-8",
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_json_path=str(context_path),
                )
            },
        )
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 47,
            "method": "tools/call",
            "params": {
                "name": "bubble_context_find",
                "arguments": {
                    "profile": "client",
                    "query": "page:index",
                    "exact": True,
                    "include_metadata": False,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "page:index"
    assert "metadata" not in payload["results"][0]


def test_execute_plan_tool_inherits_profile_app_version(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="branch-profile",
            profiles={
                "branch-profile": BubbleProfile(
                    name="branch-profile",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_version="feature-branch",
                )
            },
        )
    )
    calls = []

    def fake_execute_plan(plan, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "executed": kwargs["execute"]}

    monkeypatch.setattr(tools_module, "execute_plan", fake_execute_plan)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 48,
            "method": "tools/call",
            "params": {
                "name": "bubble_execute_plan",
                "arguments": {
                    "profile": "branch-profile",
                    "execute": True,
                    "plan": {"steps": [{"id": "s1", "args": {"write_payload": {"appname": "synthetic-app", "app_version": "test", "changes": []}}}]},
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert calls[0]["app_version"] == "feature-branch"


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


def test_completion_suggests_tool_resource_names() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 491,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/resource", "uri": "bubble://tools/{tool_name}"},
                "argument": {"name": "tool_name", "value": "create_from_h"},
            },
        }
    )

    assert response is not None
    assert response["result"]["completion"]["values"] == ["create_from_html"]


def test_completion_suggests_common_boolean_tool_arguments() -> None:
    cases = [
        ("bubble_task_runbook", "include_profile_status", "t", ["true"]),
        ("bubble_context_find", "include_metadata", "f", ["false"]),
        ("bubble_context_detect", "force", "", ["false", "true"]),
        ("create_from_html", "rendered_html", "t", ["true"]),
        ("create_from_html", "refresh_context", "f", ["false"]),
    ]

    for index, (tool_name, argument_name, value, expected) in enumerate(cases, start=1):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 490 + index,
                "method": "completion/complete",
                "params": {
                    "ref": {"type": "ref/tool", "name": tool_name},
                    "argument": {"name": argument_name, "value": value},
                },
            }
        )

        assert response is not None
        assert response["result"]["completion"]["values"] == expected


def test_completion_uses_tool_schema_suggestions() -> None:
    cases = [
        ("bubble_context_import", "kind", "b", ["bubble"]),
        ("bubble_context_detect", "app_version", "v", ["version-test"]),
        ("create_text", "app_version", "t", ["test"]),
        ("bubble_branch_create", "from_app_version", "f", ["feature-parent"]),
    ]

    for index, (tool_name, argument_name, value, expected) in enumerate(cases, start=1):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 510 + index,
                "method": "completion/complete",
                "params": {
                    "ref": {"type": "ref/tool", "name": tool_name},
                    "argument": {"name": argument_name, "value": value},
                },
            }
        )

        assert response is not None
        assert response["result"]["completion"]["values"] == expected


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
    assert "bubble_task_runbook" in message["content"]["text"]
    assert "bubble_project_bootstrap" in message["content"]["text"]
    assert "bubble_session_login" in message["content"]["text"]
    assert "Create a page" in message["content"]["text"]
    assert "Do not inspect repository code" in message["content"]["text"]


def test_prompt_get_html_import_prioritizes_runbook_and_setup_tools() -> None:
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
    assert "bubble_task_runbook" in text
    assert "bubble_project_bootstrap" in text
    assert "bubble_session_login" in text
    assert text.index("bubble_task_runbook") < text.index("create_from_html")
    assert "create_from_html" in text


def test_task_runbook_returns_route_recipe_and_tool_matches() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 54,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_runbook",
                "arguments": {
                    "task": "Convert #home-area from a URL into page mcp-01",
                    "profile": "smoke",
                    "context": "mcp-01",
                    "parent": "root",
                    "search_limit": 5,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["recipe"] == "html_import"
    assert "import_html_component" in payload["route_intents"]
    assert payload["inputs"]["profile"] == "smoke"
    assert payload["steps"][0]["tool"] == "bubble_context_detect"
    assert payload["tool_search"]["limit"] == 5
    assert "create_from_html" in [match["name"] for match in payload["tool_search"]["matches"]]
    assert "Do not inspect CLI help" in payload["usage"]
    assert response["result"]["structuredContent"] == payload


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
    assert html_route["tools"][0] == "create_from_html"
    assert "bubble_visual_audit" in html_route["tools"]


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


def test_tool_search_ignores_generic_action_noise_when_specific_terms_exist() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 260,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_search",
                "arguments": {"query": "criar página", "limit": 5},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    names = [match["name"] for match in payload["matches"]]
    assert names[0] == "create_page"
    assert "create_page" in names
    assert "create_api_token" not in names
    assert "create_301_redirect" not in names


def test_tool_search_prioritizes_visual_target_over_location_context() -> None:
    text_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 262,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_search",
                "arguments": {"query": "crie texto na página index", "limit": 5},
            },
        }
    )
    button_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 263,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_search",
                "arguments": {"query": "create button in a group", "limit": 5},
            },
        }
    )

    assert text_response is not None
    assert button_response is not None
    text_payload = json.loads(text_response["result"]["content"][0]["text"])
    button_payload = json.loads(button_response["result"]["content"][0]["text"])
    assert [match["name"] for match in text_payload["matches"]][0] == "create_text"
    assert [match["name"] for match in button_payload["matches"]][0] == "create_button"


def test_task_runbook_html_fallback_avoids_generic_create_tools() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 261,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_runbook",
                "arguments": {
                    "task": "converta o seletor #home-area da URL https://example.com/page.html para a página mcp-01",
                    "profile": "smoke",
                    "context": "mcp-01",
                    "search_limit": 8,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    names = [match["name"] for match in payload["tool_search"]["matches"]]
    assert names[:2] == ["create_from_html", "bubble_context_detect"]
    assert "create_api_token" not in names
    assert "create_301_redirect" not in names


def test_task_runbook_routes_multi_action_edits_to_inline_batch() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 264,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_runbook",
                "arguments": {
                    "task": (
                        'Na página mcp-llm do projeto cliente2, altere o texto "Bem-vindo à Aria" '
                        'para "Texto atualizado via MCP". Troque a cor primary para #808F2D. '
                        "Apague o elemento notes_input."
                    ),
                    "profile": "cliente2",
                    "context": "mcp-llm",
                    "search_limit": 6,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["recipe"] == "command_batch"
    assert payload["recommended_next_call"]["tool"] == "batch"
    assert payload["recommended_next_call"]["args"]["commands"] == "$commands"
    names = [match["name"] for match in payload["tool_search"]["matches"]]
    assert names[0] == "batch"
    assert "update_text" in names
    assert "update_color" in names
    assert "delete_multiline_input" in names


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
    assert payload["matched"]["tools"] == [
        "create_from_html",
        "bubble_context_detect",
        "bubble_visual_capture",
        "bubble_visual_capture_actual",
        "bubble_visual_audit",
    ]
    tools = [step["tool"] for step in payload["steps"]]
    assert tools == [
        "bubble_context_detect",
        "bubble_context_find",
        "create_from_html",
        "create_from_html",
        "bubble_visual_capture",
        "bubble_visual_capture_actual",
        "bubble_visual_audit",
    ]
    assert payload["steps"][1]["args"] == {
        "profile": "$profile",
        "query": "$target",
        "limit": 5,
        "exact": True,
        "include_metadata": False,
    }
    assert payload["steps"][2]["args"]["execute"] is False
    assert payload["execution_policy"]["avoid_shell_cli_discovery"] is True
    assert any("bubble_visual_audit" in gate for gate in payload["quality_gates"])
    assert any("write_count" in gate for gate in payload["quality_gates"])
    assert any("bubble_context_detect" in step for step in payload["verification"])


def test_task_runbook_routes_visual_quality_gate_to_audit_tools() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 48,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_runbook",
                "arguments": {
                    "task": "Compare o print original com o Bubble e corrija problemas visuais de fonte, imagem e gradiente",
                    "profile": "smoke",
                    "context": "mcp-01",
                    "parent": "root",
                    "search_limit": 6,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["recipe"] == "visual_quality_gate"
    assert "visual_quality_gate" in payload["route_intents"]
    assert "bubble_visual_audit" in payload["matched"]["tools"]
    assert [step["tool"] for step in payload["steps"]][-1] == "bubble_visual_audit"
    assert "bubble_visual_audit" in [match["name"] for match in payload["tool_search"]["matches"]]
    assert any("reference_screenshot" in gate for gate in payload["quality_gates"])
    assert any("rerun" in step for step in payload["verification"])


def test_task_recipe_setup_context_includes_profile_add_and_session_inspect() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 49,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_recipe",
                "arguments": {
                    "task": "setup profile cliente2 for app courselaunch and refresh context",
                    "profile": "cliente2",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["recipe"] == "setup_or_refresh_context"
    assert payload["inputs"]["profile"] == "cliente2"
    tools = [step["tool"] for step in payload["steps"]]
    assert tools[:6] == [
        "bubble_project_bootstrap",
        "bubble_profile_status",
        "bubble_profile_list",
        "bubble_profile_add",
        "bubble_session_login",
        "bubble_session_inspect",
    ]
    assert payload["steps"][0]["args"]["profile"] == "$profile"
    assert payload["steps"][0]["args"]["app_id"] == "$app_id"
    assert payload["steps"][3]["args"]["name"] == "$profile"
    assert payload["steps"][3]["args"]["app_id"] == "$app_id"
    assert payload["steps"][4]["args"]["profile"] == "$profile"
    assert payload["steps"][4]["args"]["wait_seconds"] == 180
    assert payload["steps"][5]["args"] == {"profile": "$profile"}


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


def test_task_recipe_figma_sync_requires_runtime_and_visual_parity_gate() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 54,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_recipe",
                "arguments": {
                    "task": "sincronize um componente do Figma para Bubble e compare com o print original",
                    "profile": "smoke",
                    "context": "mcp-01",
                    "parent": "root",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["recipe"] == "visual_quality_gate"
    route_tools = {
        tool
        for route in payload["recommended_routes"]
        if route["intent"] == "manage_styles_tokens_design_system"
        for tool in route["tools"]
    }
    assert "sync_figma_component" in route_tools
    assert "sync_component" in route_tools
    assert any("structured snapshots" in gate for gate in payload["quality_gates"])
    assert any("bubble_visual_audit" in step for step in payload["verification"])


def test_agent_routing_does_not_treat_bubble_version_test_as_quality_gate() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 51,
            "method": "tools/call",
            "params": {
                "name": "bubble_agent_guide",
                "arguments": {"task": "liste as branches e busque o changelog da versão test"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    intents = {route["intent"] for route in payload["recommended_routes"]}
    assert "branches_or_changelog" in intents
    assert "check_server_or_catalog" not in intents


def test_task_recipe_prioritizes_visual_element_over_page_target() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 52,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_recipe",
                "arguments": {"task": "crie um texto na página index", "context": "index"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["recipe"] == "visual_edit"


def test_agent_routing_uses_token_keywords_not_substrings() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 53,
            "method": "tools/call",
            "params": {
                "name": "bubble_agent_guide",
                "arguments": {"task": "faça login da sessão e detecte o contexto atualizado do projeto"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    intents = {route["intent"] for route in payload["recommended_routes"]}
    assert intents == {"find_profile_session_or_context"}


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
    assert recipe["steps"][1]["tool"] == "bubble_context_find"
    assert recipe["steps"][1]["args"]["exact"] is True
    assert recipe["steps"][1]["args"]["include_metadata"] is False
    assert "create_page" in [match["name"] for match in search["matches"]]


def test_agent_routing_understands_project_transfer() -> None:
    guide_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 86,
            "method": "tools/call",
            "params": {
                "name": "bubble_agent_guide",
                "arguments": {"task": "copie o reusable Header do profile template para o profile cliente2"},
            },
        }
    )
    runbook_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 87,
            "method": "tools/call",
            "params": {
                "name": "bubble_task_runbook",
                "arguments": {
                    "task": "copie o reusable Header do profile template para o profile cliente2",
                    "profile": "cliente2",
                    "search_limit": 5,
                },
            },
        }
    )

    assert guide_response is not None
    assert runbook_response is not None
    guide = json.loads(guide_response["result"]["content"][0]["text"])
    runbook = json.loads(runbook_response["result"]["content"][0]["text"])
    route_intents = {route["intent"] for route in guide["recommended_routes"]}
    assert "transfer_between_projects" in route_intents
    assert runbook["recipe"] == "project_transfer"
    assert runbook["recommended_next_call"]["tool"] == "bubble_profile_status"
    assert "bubble_transfer_plan" in [match["name"] for match in runbook["tool_search"]["matches"]]
    assert "bubble_transfer_execute" in runbook["matched"]["tools"]


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
    assert payload["summary"]["passed"] == 9
    assert all("bubble_task_runbook" in result["tool"] for result in payload["results"])


def test_runtime_smoke_tool_runs_visual_repair_suite() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 47,
            "method": "tools/call",
            "params": {"name": "bubble_runtime_smoke", "arguments": {"suite": "visual-repair"}},
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["suite"] == "visual-repair"
    assert payload["summary"] == {"cases": 1, "passed": 1, "failed": 0, "skipped": 0}
    assert payload["results"][0]["tool"] == "bubble_visual_audit"


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
    assert "visual_quality_gate" in recipe["inputSchema"]["properties"]["recipe"]["enum"]
    properties = smoke["inputSchema"]["properties"]
    assert "visual-repair" in properties["suite"]["enum"]
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


def test_create_styles_from_html_catalog_tool_uses_style_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_styles_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "style_count": 1, "operation_count": 3, "executed": kwargs["execute"]}

    monkeypatch.setattr("bubble_mcp.server.tools.create_styles_from_html_runtime", fake_create_styles_from_html_runtime)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "create_styles_from_html",
                "arguments": {
                    "profile": "smoke",
                    "html_file": "tests/fixtures/html/style-states.html",
                    "execute": True,
                    "selector": ".btn-primary",
                    "style_name": "Primary Button",
                    "element_type": "Button",
                    "states": ["hover", "focus"],
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["style_count"] == 1
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["html_file"] == "tests/fixtures/html/style-states.html"
    assert calls[0]["execute"] is True
    assert calls[0]["selector"] == ".btn-primary"
    assert calls[0]["style_name"] == "Primary Button"
    assert calls[0]["element_type"] == "Button"
    assert calls[0]["states"] == ["hover", "focus"]


def test_create_styles_from_html_execute_dispatches_style_operations(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_dispatch(tool_name, args):  # type: ignore[no-untyped-def]
        calls.append((tool_name, args))
        return {"ok": True, "tool": tool_name}

    monkeypatch.setattr("bubble_mcp.server.tools.dispatch_aria_runtime_tool", fake_dispatch)
    monkeypatch.setattr(
        "bubble_mcp.server.tools._verify_html_style_import",
        lambda _profile, candidate: {
            "ok": True,
            "style_name": candidate["name"],
            "element_type": candidate["element_type"],
        },
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "create_styles_from_html",
                "arguments": {
                    "profile": "smoke",
                    "html": """
                    <style>
                      .btn-primary { color: #ffffff; }
                      .btn-primary:hover { color: #eeeeee; }
                    </style>
                    """,
                    "execute": True,
                    "selector": ".btn-primary",
                    "style_name": "Primary Button",
                    "element_type": "Button",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["executed"] is True
    assert payload["verified"] is True
    assert [tool for tool, _args in calls] == [
        "create_style",
        "add_style_condition",
        "reorder_style_states",
    ]
    assert calls[0][1]["execute"] is True
    assert calls[0][1]["dry_run"] is False


def test_html_style_import_verification_reads_refreshed_context(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "metadata": {
                    "styles": {
                        "Button_primary_button_": {
                            "name": "Primary Button",
                            "type": "Button",
                            "%p": {"%bgc": "#155eef", "%fc": "#ffffff"},
                            "%s": {
                                "hover_state": {
                                    "%c": {
                                        "%x": "ThisElement",
                                        "%n": {"%x": "Message", "%nm": "is_hovered"},
                                    },
                                    "%p": {"%bgc": "#004eeb"},
                                }
                            },
                        }
                    }
                },
                "nodes": [],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        tools_module,
        "_profile_cache_refresh",
        lambda _args: {
            "ok": True,
            "source": "bubble",
            "app_id": "synthetic-app",
            "app_version": "test",
            "context_detection": {"context_path": str(context_path)},
        },
    )

    result = tools_module._verify_html_style_import(
        "smoke",
        {
            "name": "Primary Button",
            "element_type": "Button",
            "base": {"bg_color": "#155eef", "font_color": "#ffffff"},
            "states": {"hover": {"bg_color": "#004eeb"}},
        },
    )

    assert result["ok"] is True
    assert result["style"]["id"] == "Button_primary_button_"
    assert result["expected_states"] == ["hover"]
    assert result["property_check"]["checked"] is True
    assert result["state_check"]["properties"]["hover"]["checked"] is True


def test_html_style_import_verification_checks_normalized_context_properties(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "metadata": {
                    "styles": {
                        "Text_htmltitle_": {
                            "display": "html-title",
                            "type": "Text",
                            "properties": {
                                "bgcolor": "rgba(0, 0, 0, 0)",
                                "font_size": 72,
                                "font_weight": "700",
                                "border_roundness": 0,
                            },
                        }
                    }
                },
                "nodes": [],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        tools_module,
        "_profile_cache_refresh",
        lambda _args: {
            "ok": True,
            "source": "bubble",
            "app_id": "synthetic-app",
            "app_version": "test",
            "context_detection": {"context_path": str(context_path)},
        },
    )

    result = tools_module._verify_html_style_import(
        "smoke",
        {
            "name": "html-title",
            "element_type": "Text",
            "base": {
                "bg_color": "rgba(0, 0, 0, 0)",
                "font_size": 72,
                "font_weight": "700",
                "border_radius": 0,
            },
            "states": {},
        },
    )

    assert result["ok"] is True
    assert result["property_check"]["checked"] is True
    assert result["property_check"]["missing"] == []


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


def test_batch_dispatch_accepts_inline_commands(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    class FakePayloadBuilder:
        send_to_webhook = None
        to_json = None

    class FakeBubbleSdk:
        PayloadBuilder = FakePayloadBuilder

    class FakeBubbleCliModule:
        inquirer = None

        class BubbleCLI:
            def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                calls.append(("init", kwargs))

            def process_batch(self, file_path, dry_run=False):  # type: ignore[no-untyped-def]
                calls.append(("process_batch", {"file_path": file_path, "dry_run": dry_run}))
                return False

            def execute_commands(self, commands, dry_run=False):  # type: ignore[no-untyped-def]
                calls.append(("execute_commands", {"commands": commands, "dry_run": dry_run}))
                return True

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

    commands = [
        {"command": "update-text", "context": "mcp-llm", "search_text": "Bem-vindo", "new_text": "Texto atualizado"},
        {"command": "update-color", "name": "primary", "rgba": "#808F2D"},
        {"command": "delete-multiline-input", "context": "mcp-llm", "element_name": "notes_input"},
    ]
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 110,
            "method": "tools/call",
            "params": {
                "name": "batch",
                "arguments": {
                    "profile": "smoke",
                    "app_id": "synthetic-app",
                    "commands": commands,
                    "execute": False,
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["engine"] == "aria_runtime"
    assert payload["executed"] is False
    assert calls[0][0] == "init"
    assert calls[1] == ("execute_commands", {"commands": commands, "dry_run": True})


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
    style_schema = next(tool for tool in tools if tool["name"] == "create_styles_from_html")
    assert "hover" in style_schema["description"]


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

    html_style_import = tools["create_styles_from_html"]["inputSchema"]
    assert html_style_import["required"] == ["profile", "style_name", "element_type"]
    assert html_style_import["anyOf"] == [
        {"required": ["url"]},
        {"required": ["html_file"]},
        {"required": ["file"]},
        {"required": ["html"]},
    ]
    assert html_style_import["properties"]["url"]["type"] == "string"
    assert "Bubble element type" in html_style_import["properties"]["element_type"]["description"]
    assert "style_name" in html_style_import["properties"]
    assert html_style_import["properties"]["rendered_html"]["type"] == "boolean"
    assert html_style_import["properties"]["include_states"]["type"] == "boolean"
    assert html_style_import["properties"]["states"]["items"]["enum"] == ["hover", "focus", "disabled", "pressed"]

    session_import = tools["bubble_session_import"]["inputSchema"]
    assert session_import["properties"]["session"]["properties"]["headers"]["type"] == "object"
    assert session_import["properties"]["session"]["properties"]["url"]["format"] == "uri"

    session_inspect = tools["bubble_session_inspect"]["inputSchema"]
    assert session_inspect["required"] == ["profile"]
    assert "app_id" in session_inspect["properties"]

    session_login = tools["bubble_session_login"]["inputSchema"]
    assert session_login["required"] == ["profile"]
    assert session_login["properties"]["wait_seconds"]["default"] == 180
    assert session_login["properties"]["headless"]["default"] is False

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
    assert schema["x-bubble-defaults"]["layout"] == "column"
    assert schema["x-bubble-name-prefix"] == "gp_"
    assert schema["x-bubble-element-type"] == "Group"
    assert schema["properties"]["name"]["examples"] == ["gp_example"]
    assert schema["properties"]["fit_height"]["default"] is True
    assert schema["properties"]["min_height"]["default"] == 40
    assert schema["properties"]["min_width"]["default"] == 40
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

    create_text = tools["create_text"]["inputSchema"]
    assert create_text["required"] == ["profile", "context", "parent", "content"]
    assert create_text["x-bubble-name-prefix"] == "tx_"
    assert create_text["properties"]["fit_height"]["default"] is True
    assert create_text["properties"]["name"]["examples"] == ["tx_example"]

    create_image = tools["create_image"]["inputSchema"]
    assert create_image["x-bubble-name-prefix"] == "im_"
    assert create_image["properties"]["width"]["default"] == 120
    assert create_image["properties"]["fixed_width"]["default"] is True
    assert create_image["properties"]["min_height"]["default"] == 64

    create_video = tools["create_video"]["inputSchema"]
    assert create_video["properties"]["use_aspect_ratio"]["default"] is True
    assert create_video["properties"]["aspect_ratio_width"]["default"] == 16
    assert create_video["properties"]["aspect_ratio_height"]["default"] == 9

    create_style = tools["create_style"]["inputSchema"]
    assert create_style["required"] == ["profile", "name", "element_type"]
    for field in ["map_type", "custom_style", "border_radius"]:
        assert field in create_style["properties"]

    delete_data_field = tools["delete_data_field"]["inputSchema"]
    assert delete_data_field["required"] == ["profile", "data_type_ref", "name"]
    assert "x-bubble-data-field-key-guidance" in delete_data_field
    delete_field_description = delete_data_field["properties"]["name"]["description"]
    assert "Exact Bubble schema field key" in delete_field_description
    assert "field_name_text" in delete_field_description
    assert "field_name_number" in delete_field_description
    assert "nome_do_campo_tabelarelacional" in delete_field_description

    create_event = tools["create_event"]["inputSchema"]
    assert create_event["required"] == ["profile", "context", "event_type"]
    for field in ["only_when_json", "interval_seconds", "element_ref", "event_key"]:
        assert field in create_event["properties"]

    add_action = tools["add_action"]["inputSchema"]
    assert add_action["required"] == ["profile", "context", "action_type"]

    login = tools["log_the_user_in"]["inputSchema"]
    assert login["required"] == ["profile", "context", "event_ref", "email_input_ref", "password_input_ref"]
    for field in ["workflow_id", "action_index", "stay_logged_in", "remember_email", "app_id", "execute"]:
        assert field in login["properties"]

    social = tools["signup_login_with_a_social_network"]["inputSchema"]
    assert social["required"] == ["profile", "context", "event_ref", "oauth_provider"]
    assert social["properties"]["oauth_provider"]["enum"] == ["google", "facebook"]
    assert social["properties"]["provider_app_secret"]["description"]

    change_user = tools["make_changes_to_current_user"]["inputSchema"]
    assert change_user["required"] == ["profile", "context", "event_ref", "fields"]
    assert "field_name_text" in change_user["properties"]["fields"]["description"]
    for field in ["fields", "thing", "to_email", "query_json"]:
        assert field in add_action["properties"]

    create_privacy_rule = tools["create_privacy_rule"]["inputSchema"]
    assert create_privacy_rule["required"] == ["profile", "data_type_ref"]
    for field in ["rule_key", "rule_name", "view_all", "view_fields", "binding_fields", "condition_json"]:
        assert field in create_privacy_rule["properties"]
    assert "field_name_text" in create_privacy_rule["properties"]["view_fields"]["description"]
    assert "field_name_text" in create_privacy_rule["properties"]["binding_fields"]["description"]

    set_privacy_rule_permission = tools["set_privacy_rule_permission"]["inputSchema"]
    assert set_privacy_rule_permission["required"] == ["profile", "data_type_ref", "rule_key", "permission", "value"]
    assert set_privacy_rule_permission["properties"]["permission"]["enum"] == [
        "view_all",
        "view_attachments",
        "search_for",
        "auto_binding",
    ]

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
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_version="feature-branch",
                )
            },
        )
    )
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

    def fake_write(self, write_payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "dry_run": dry_run,
            "calculate_derived": calculate_derived,
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
    assert result["request"]["payload"]["app_version"] == "feature-branch"

    overlay_path = tmp_path / "contexts" / "smoke" / "synthetic-app-mutation-overlay.json"
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    assert overlay["entries"][0]["source"] == "bubble_editor_write"
    assert overlay["entries"][0]["changes"][0]["path_array"] == ["%p3", "mcp01"]


def test_tools_list_includes_full_aria_catalog() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})

    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert len(ARIA_BUBBLE_TOOL_NAMES) == 213
    assert set(ARIA_BUBBLE_TOOL_NAMES).issubset(names)
    assert "delete_data_field" in names
    assert "create_privacy_rule" in names
    assert "set_privacy_rule_field_visibility" in names
    assert "delete_privacy_rule" in names


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


def test_direct_auth_catalog_tool_call_compiles_and_redacts_oauth_secret() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "signup_login_with_a_social_network",
                "arguments": {
                    "profile": "smoke",
                    "app_id": "synthetic-app",
                    "context": "index",
                    "event_ref": "wf_oauth",
                    "oauth_provider": "google",
                    "provider_app_id": "google-client-id",
                    "provider_app_secret": "google-secret",
                },
            },
        }
    )

    assert response is not None
    raw_text = response["result"]["content"][0]["text"]
    assert "google-secret" not in raw_text
    payload = json.loads(raw_text)
    write_payload = payload["results"][0]["payload"]
    create_action = first_change(write_payload, "CreateAction")
    assert create_action["body"]["0"]["%x"] == "OAuthLogin"
    assert create_action["body"]["0"]["%p"]["oauth_provider"] == "google"
    settings = [change for change in write_payload["changes"] if change.get("intent", {}).get("name") == "ChangeAppSetting"]
    assert ["settings", "client_safe", "google_appid"] in [change["path_array"] for change in settings]
    secret_change = next(change for change in settings if change["path_array"] == ["settings", "secure", "google_appsecret"])
    assert secret_change["body"] == "[REDACTED]"


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


def test_extension_management_tools_are_listed() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 100, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert tools["bubble_extension_list"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_extension_list"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_extension_import"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_extension_import"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_extension_enable"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_extension_enable"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_extension_disable"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_extension_disable"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_extension_validate"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_extension_validate"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_extension_call"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_extension_call"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_extension_companion_start"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_extension_companion_start"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_extension_companion_start"]["annotations"]["openWorldHint"] is True
    assert tools["bubble_extension_companion_start"]["inputSchema"]["properties"]["port"]["default"] == 3847
    assert tools["bubble_extension_companion_status"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_extension_companion_stop"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_tool_wizard_activate"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_tool_wizard_activate"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_tool_wizard_activate"]["inputSchema"]["required"] == ["session_id"]


def test_extension_management_tools_are_searchable() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 104,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_search",
                "arguments": {"query": "extension pack list validate import enable disable", "limit": 15},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    matches = {match["name"] for match in payload["matches"]}
    assert {
        "bubble_extension_list",
        "bubble_extension_validate",
        "bubble_extension_import",
        "bubble_extension_enable",
        "bubble_extension_disable",
        "bubble_extension_call",
    }.issubset(matches)

    companion_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 105,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_search",
                "arguments": {"query": "companion listener", "limit": 5},
            },
        }
    )
    assert companion_response is not None
    companion_payload = json.loads(companion_response["result"]["content"][0]["text"])
    companion_matches = {match["name"] for match in companion_payload["matches"]}
    assert {
        "bubble_extension_companion_start",
        "bubble_extension_companion_status",
        "bubble_extension_companion_stop",
    }.issubset(companion_matches)


def test_extension_list_tool_returns_installed_extensions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {"name": "bubble_extension_list", "arguments": {}},
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload == {"ok": True, "extensions": []}


def test_extension_companion_mcp_tools_start_status_and_stop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    try:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 102,
                "method": "tools/call",
                "params": {
                    "name": "bubble_extension_companion_start",
                    "arguments": {"port": 0},
                },
            }
        )

        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        assert payload["ok"] is True
        assert payload["running"] is True
        assert payload["port"] > 0

        status_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 103,
                "method": "tools/call",
                "params": {"name": "bubble_extension_companion_status", "arguments": {}},
            }
        )
        assert status_response is not None
        status = json.loads(status_response["result"]["content"][0]["text"])
        assert status["running"] is True
        assert status["port"] == payload["port"]
    finally:
        stop_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 104,
                "method": "tools/call",
                "params": {"name": "bubble_extension_companion_stop", "arguments": {}},
            }
        )
        assert stop_response is not None
        stopped = json.loads(stop_response["result"]["content"][0]["text"])
        assert stopped["ok"] is True
        assert stopped["running"] is False


def test_extension_management_tools_validate_required_arguments() -> None:
    for tool_name, required_arg in (
        ("bubble_extension_validate", "path"),
        ("bubble_extension_import", "path"),
        ("bubble_extension_enable", "extension_id"),
        ("bubble_extension_disable", "extension_id"),
    ):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 102,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": {}},
            }
        )

        assert response is not None
        result = response["result"]
        payload = json.loads(result["content"][0]["text"])
        assert result["isError"] is True
        assert payload["ok"] is False
        assert payload["tool"] == tool_name
        assert payload["error"] == f"{tool_name} requires {required_arg}."


def test_learning_tools_are_listed_with_annotations() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 103, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert tools["bubble_learning_record"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_learning_record"]["annotations"]["idempotentHint"] is False
    assert tools["bubble_learning_list"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_learning_list"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_learning_record"]["inputSchema"]["required"] == [
        "scope",
        "key",
        "source",
        "confidence",
    ]


def test_knowledge_tools_are_listed_with_annotations() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 110, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    for name in (
        "bubble_knowledge_search",
        "bubble_knowledge_fetch",
        "bubble_manual_guidance",
        "bubble_manual_context_for_tool_authoring",
        "bubble_manual_context_for_validation",
    ):
        assert tools[name]["annotations"]["readOnlyHint"] is True
        assert tools[name]["annotations"]["idempotentHint"] is True
    assert tools["bubble_knowledge_refresh_source"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_knowledge_refresh_source"]["annotations"]["idempotentHint"] is False
    assert tools["bubble_knowledge_search"]["inputSchema"]["required"] == ["query"]
    assert tools["bubble_knowledge_fetch"]["inputSchema"]["required"] == ["record_id"]
    assert tools["bubble_knowledge_refresh_source"]["inputSchema"]["required"] == ["source", "file"]


def test_framework_tools_are_listed_with_annotations() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 113, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert tools["bubble_framework_list"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_framework_status"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_framework_generate_artifacts"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_framework_sync_evidence"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_framework_generate_artifacts"]["inputSchema"]["required"] == [
        "framework",
        "profile",
        "objective",
    ]
    assert tools["bubble_framework_sync_evidence"]["inputSchema"]["required"] == [
        "framework",
        "profile",
        "evidence",
    ]


def test_framework_tools_generate_sync_and_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    generate_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 114,
            "method": "tools/call",
            "params": {
                "name": "bubble_framework_generate_artifacts",
                "arguments": {
                    "framework": "bmad",
                    "profile": "cliente2",
                    "objective": "Plan checkout",
                    "context_summary": {"pages": 2},
                },
            },
        }
    )

    assert generate_response is not None
    generated = json.loads(generate_response["result"]["content"][0]["text"])
    assert generated["ok"] is True
    assert generated["framework"] == "bmad"
    assert generated["artifacts"]

    sync_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 115,
            "method": "tools/call",
            "params": {
                "name": "bubble_framework_sync_evidence",
                "arguments": {
                    "framework": "bmad",
                    "profile": "cliente2",
                    "artifact_dir": generated["artifact_dir"],
                    "evidence": {"summary": "Preview passed", "token": "secret"},
                },
            },
        }
    )

    assert sync_response is not None
    synced = json.loads(sync_response["result"]["content"][0]["text"])
    assert synced["ok"] is True

    status_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 116,
            "method": "tools/call",
            "params": {"name": "bubble_framework_status", "arguments": {"framework": "bmad", "profile": "cliente2"}},
        }
    )

    assert status_response is not None
    status = json.loads(status_response["result"]["content"][0]["text"])
    assert status["ok"] is True
    assert status["status"][0]["artifact_count"] == 1
    assert status["status"][0]["evidence_count"] == 1


def test_language_tools_are_listed_with_annotations() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 201, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    for name in (
        "bubble_language_index",
        "bubble_language_query",
        "bubble_language_tool_detail",
        "bubble_language_diff",
        "bubble_framework_language_pack",
        "bubble_framework_compile_program",
    ):
        assert name in tools
    assert tools["bubble_language_index"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_language_query"]["inputSchema"]["required"] == ["query"]
    assert tools["bubble_language_tool_detail"]["inputSchema"]["required"] == ["tools"]
    assert tools["bubble_framework_language_pack"]["inputSchema"]["required"] == ["framework"]
    assert tools["bubble_framework_compile_program"]["inputSchema"]["required"] == [
        "framework",
        "profile",
        "program",
    ]


def test_language_tools_dispatch_index_query_pack_and_compile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    index_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 202,
            "method": "tools/call",
            "params": {"name": "bubble_language_index", "arguments": {"profile": "cliente2"}},
        }
    )
    assert index_response is not None
    index_payload = json.loads(index_response["result"]["content"][0]["text"])
    assert index_payload["registry_version"].startswith("sha256:")

    query_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 203,
            "method": "tools/call",
            "params": {
                "name": "bubble_language_query",
                "arguments": {"query": "create button", "families": ["visual_editor"], "limit": 5},
            },
        }
    )
    assert query_response is not None
    query_payload = json.loads(query_response["result"]["content"][0]["text"])
    assert query_payload["matches"]

    pack_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 204,
            "method": "tools/call",
            "params": {
                "name": "bubble_framework_language_pack",
                "arguments": {"framework": "bmad", "profile": "cliente2", "scope": "create checkout button"},
            },
        }
    )
    assert pack_response is not None
    pack_payload = json.loads(pack_response["result"]["content"][0]["text"])
    assert pack_payload["framework"] == "bmad"

    compile_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 205,
            "method": "tools/call",
            "params": {
                "name": "bubble_framework_compile_program",
                "arguments": {
                    "framework": "bmad",
                    "profile": "cliente2",
                    "program": {
                        "objective": "Create CTA",
                        "steps": [
                            {
                                "tool": "create_button",
                                "arguments": {"context": "index", "parent": "root", "label": "Start"},
                            }
                        ],
                    },
                },
            },
        }
    )
    assert compile_response is not None
    compile_payload = json.loads(compile_response["result"]["content"][0]["text"])
    assert compile_payload["ok"] is True
    assert compile_payload["compiled_calls"][0]["arguments"]["execute"] is False


def test_high_potential_tools_include_docs_enrichment_metadata() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 111, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    expected = {
        "create_api_token": ("api_connector", 5),
        "delete_data_field": ("data_schema", 5),
        "create_workflow": ("workflow", 5),
        "bubble_performance_audit": ("observability", 4),
        "edit_style": ("style_design", 4),
        "create_button": ("visual_editor", 3),
        "bubble_branch_list": ("branch_version", 3),
        "bubble_tool_wizard_generate": ("extension_authoring", 4),
    }
    for tool_name, (family, priority) in expected.items():
        docs = tools[tool_name]["inputSchema"]["x-bubble-docs"]
        assert docs["family"] == family
        assert docs["priority"] == priority
        assert docs["manual_context_tool"] == "bubble_manual_context_for_tool_authoring"
        assert docs["recommended_queries"]
        assert "never authorizes execution" in docs["source_policy"]
        assert f"Docs-enrichment family: {family}." in tools[tool_name]["description"]


def test_tool_search_returns_docs_enrichment_hints() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 112,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_search",
                "arguments": {"query": "API Connector authentication credentials", "limit": 5},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    matches = {match["name"]: match for match in payload["matches"]}
    docs = matches["create_api_token"]["docs_enrichment"]
    assert docs["family"] == "api_connector"
    assert docs["priority"] == 5
    assert docs["recommended_queries"][0] == "API Connector authentication reusable calls private credentials"


def test_tool_wizard_tools_are_listed_with_annotations() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 120, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert tools["bubble_tool_wizard_start"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_tool_wizard_start"]["annotations"]["idempotentHint"] is False
    assert tools["bubble_tool_wizard_add_capture"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_tool_wizard_add_capture"]["annotations"]["idempotentHint"] is False
    assert tools["bubble_tool_wizard_describe"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_tool_wizard_describe"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_tool_wizard_finalize"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_tool_wizard_finalize"]["annotations"]["idempotentHint"] is False
    assert tools["bubble_tool_wizard_generate"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_tool_wizard_generate"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_tool_wizard_start"]["inputSchema"]["required"] == ["intent", "target", "profile"]
    assert tools["bubble_tool_wizard_add_capture"]["inputSchema"]["required"] == ["session_id", "file"]
    assert tools["bubble_tool_wizard_describe"]["inputSchema"]["required"] == ["session_id"]
    assert tools["bubble_tool_wizard_finalize"]["inputSchema"]["required"] == ["session_id"]
    assert "generate_pack" in tools["bubble_tool_wizard_finalize"]["inputSchema"]["properties"]
    assert tools["bubble_tool_wizard_generate"]["inputSchema"]["required"] == ["session_id"]


def test_tool_wizard_tools_start_add_capture_and_describe(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    start_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 121,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_start",
                "arguments": {
                    "intent": "Create an API Connector call",
                    "target": "api_connector",
                    "profile": "client",
                },
            },
        }
    )

    assert start_response is not None
    start_payload = json.loads(start_response["result"]["content"][0]["text"])
    assert start_payload["ok"] is True
    assert start_payload["active"] is True
    assert start_payload["workflow"]["finish_with"] == "bubble_tool_wizard_finalize"
    session_id = start_payload["session"]["id"]

    add_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 122,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_add_capture",
                "arguments": {
                    "session_id": session_id,
                    "file": "tests/fixtures/tool-authoring/api-connector-write-capture.json",
                },
            },
        }
    )

    assert add_response is not None
    add_payload = json.loads(add_response["result"]["content"][0]["text"])
    assert add_payload["ok"] is True
    assert add_payload["classification"]["families"] == ["editor_write"]
    assert add_payload["classification"]["change_count"] == 1

    describe_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 123,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_describe",
                "arguments": {"session_id": session_id},
            },
        }
    )

    assert describe_response is not None
    describe_payload = json.loads(describe_response["result"]["content"][0]["text"])
    assert describe_payload["session"]["intent"] == "Create an API Connector call"
    assert describe_payload["classification"]["app_id"] == "synthetic-app"
    assert describe_payload["classification"]["change_count"] == 1

    finalize_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 126,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_finalize",
                "arguments": {"session_id": session_id},
            },
        }
    )

    assert finalize_response is not None
    finalize_payload = json.loads(finalize_response["result"]["content"][0]["text"])
    assert finalize_payload["ok"] is True
    assert finalize_payload["status"] == "ready_for_review"
    assert finalize_payload["capture_summary"]["intents"] == ["CreateApiConnectorCall"]
    assert finalize_payload["questions"]
    assert finalize_payload["testing_guidance"]
    assert finalize_payload["next_mcp_calls"][0]["tool"] == "bubble_tool_wizard_generate"

    finalize_generate_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 131,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_finalize",
                "arguments": {"session_id": session_id, "generate_pack": True},
            },
        }
    )
    assert finalize_generate_response is not None
    finalize_generate_payload = json.loads(finalize_generate_response["result"]["content"][0]["text"])
    assert finalize_generate_payload["ok"] is True
    assert finalize_generate_payload["validation"]["ok"] is True
    assert finalize_generate_payload["next_mcp_calls"][3]["tool"] == "bubble_extension_call"

    generate_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 127,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_generate",
                "arguments": {"session_id": session_id},
            },
        }
    )

    assert generate_response is not None
    generate_payload = json.loads(generate_response["result"]["content"][0]["text"])
    assert generate_payload["ok"] is True
    assert generate_payload["validation"]["ok"] is True
    assert generate_payload["pack_path"]

    import_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 128,
            "method": "tools/call",
            "params": {
                "name": "bubble_extension_import",
                "arguments": {"path": generate_payload["pack_path"]},
            },
        }
    )
    assert import_response is not None
    assert json.loads(import_response["result"]["content"][0]["text"])["ok"] is True

    enable_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 129,
            "method": "tools/call",
            "params": {
                "name": "bubble_extension_enable",
                "arguments": {"extension_id": generate_payload["extension_id"]},
            },
        }
    )
    assert enable_response is not None
    assert json.loads(enable_response["result"]["content"][0]["text"])["ok"] is True

    preview_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 130,
            "method": "tools/call",
            "params": {
                "name": "bubble_extension_call",
                "arguments": {
                    "tool": generate_payload["tool_name"],
                    "arguments": {
                        "profile": "client",
                        "name": "Get Products",
                        "method": "GET",
                        "url": "https://api.example.invalid/products",
                        "execute": False,
                    },
                },
            },
        }
    )
    assert preview_response is not None
    preview_payload = json.loads(preview_response["result"]["content"][0]["text"])
    assert preview_payload["ok"] is True
    assert preview_payload["execute"] is False
    assert preview_payload["extension_id"] == generate_payload["extension_id"]


def test_tool_wizard_add_capture_returns_structured_mcp_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    no_payload = tmp_path / "no-payload.json"
    no_payload.write_text("{}", encoding="utf-8")

    start_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 124,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_start",
                "arguments": {
                    "intent": "Create an API Connector call",
                    "target": "api_connector",
                    "profile": "client",
                },
            },
        }
    )
    assert start_response is not None
    session_id = json.loads(start_response["result"]["content"][0]["text"])["session"]["id"]

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 125,
            "method": "tools/call",
            "params": {
                "name": "bubble_tool_wizard_add_capture",
                "arguments": {
                    "session_id": session_id,
                    "file": str(no_payload),
                },
            },
        }
    )

    assert response is not None
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    assert result["isError"] is True
    assert payload["ok"] is False
    assert payload["tool"] == "bubble_tool_wizard_add_capture"
    assert payload["error_class"] == "ValueError"
    assert "does not contain a Bubble editor write body" in payload["error"]


def test_knowledge_tools_import_search_and_fetch_local_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    refresh_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 111,
            "method": "tools/call",
            "params": {
                "name": "bubble_knowledge_refresh_source",
                "arguments": {
                    "source": "bubble_manual_gitbook",
                    "file": "tests/fixtures/knowledge/bubble-manual-records.jsonl",
                },
            },
        }
    )

    assert refresh_response is not None
    refresh_payload = json.loads(refresh_response["result"]["content"][0]["text"])
    assert refresh_payload["ok"] is True
    assert refresh_payload["imported"] == 2

    search_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 112,
            "method": "tools/call",
            "params": {
                "name": "bubble_manual_guidance",
                "arguments": {"query": "privacy rules migration", "limit": 3},
            },
        }
    )

    assert search_response is not None
    search_payload = json.loads(search_response["result"]["content"][0]["text"])
    assert search_payload["ok"] is True
    assert search_payload["purpose"] == "manual_guidance"
    assert search_payload["cache_only"] is True
    assert search_payload["results"][0]["id"] == "bubble-manual:data-types:privacy"

    fetch_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 113,
            "method": "tools/call",
            "params": {
                "name": "bubble_knowledge_fetch",
                "arguments": {"record_id": "bubble-manual:data-types:privacy"},
            },
        }
    )

    assert fetch_response is not None
    fetch_payload = json.loads(fetch_response["result"]["content"][0]["text"])
    assert fetch_payload["ok"] is True
    assert fetch_payload["record"]["source_url"].startswith("https://manual.bubble.io/")


def test_learning_tools_append_and_list_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    record_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 104,
            "method": "tools/call",
            "params": {
                "name": "bubble_learning_record",
                "arguments": {
                    "scope": "project",
                    "key": "naming.page_language",
                    "value": {"language": "pt-BR"},
                    "source": "user_declared",
                    "confidence": "confirmed",
                    "project": "client-app",
                },
            },
        }
    )

    assert record_response is not None
    record_payload = json.loads(record_response["result"]["content"][0]["text"])
    assert record_payload["ok"] is True
    assert record_payload["record"]["scope"] == "project"
    assert record_payload["record"]["project"] == "client-app"

    list_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 105,
            "method": "tools/call",
            "params": {
                "name": "bubble_learning_list",
                "arguments": {"scope": "project", "project": "client-app"},
            },
        }
    )

    assert list_response is not None
    list_payload = json.loads(list_response["result"]["content"][0]["text"])
    assert list_payload["ok"] is True
    assert [record["key"] for record in list_payload["records"]] == ["naming.page_language"]


def test_learning_record_tool_rejects_missing_scope_discriminator_without_append(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 106,
            "method": "tools/call",
            "params": {
                "name": "bubble_learning_record",
                "arguments": {
                    "scope": "project",
                    "key": "naming.page_language",
                    "value": {"language": "pt-BR"},
                    "source": "user_declared",
                    "confidence": "confirmed",
                },
            },
        }
    )

    assert response is not None
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    assert result["isError"] is True
    assert payload["ok"] is False
    assert payload["tool"] == "bubble_learning_record"
    assert payload["error"] == "Learning record scope 'project' requires project."

    list_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 107,
            "method": "tools/call",
            "params": {"name": "bubble_learning_list", "arguments": {}},
        }
    )
    assert list_response is not None
    list_payload = json.loads(list_response["result"]["content"][0]["text"])
    assert list_payload["records"] == []


def test_learning_record_tool_rejects_non_object_value_without_append(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 108,
            "method": "tools/call",
            "params": {
                "name": "bubble_learning_record",
                "arguments": {
                    "scope": "global",
                    "key": "workflow.preview_required",
                    "value": True,
                    "source": "user_declared",
                    "confidence": "confirmed",
                },
            },
        }
    )

    assert response is not None
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    assert result["isError"] is True
    assert payload["ok"] is False
    assert payload["tool"] == "bubble_learning_record"
    assert payload["error"] == "bubble_learning_record requires value to be a JSON object."

    list_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 109,
            "method": "tools/call",
            "params": {"name": "bubble_learning_list", "arguments": {}},
        }
    )
    assert list_response is not None
    list_payload = json.loads(list_response["result"]["content"][0]["text"])
    assert list_payload["records"] == []
