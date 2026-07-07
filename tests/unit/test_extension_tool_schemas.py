import json
import shutil
from pathlib import Path

from bubble_mcp.extensions.store import enable_extension, import_extension
from bubble_mcp.extensions.tools import enabled_extension_tool_schemas
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.learning.store import append_learning_record
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.server.tools import call_tool
from bubble_mcp.sessions.store import save_session, session_from_payload
from bubble_mcp.tool_authoring.sessions import (
    append_capture_to_authoring_session,
    create_authoring_session,
    generate_authoring_extension_pack,
)


SIMPLE_PACK = Path("tests/fixtures/extensions/simple-pack")


def test_enabled_extension_tool_schema_is_additive(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(SIMPLE_PACK)
    enable_extension("local.simple-pack")

    tools = {tool["name"]: tool for tool in enabled_extension_tool_schemas()}

    assert "local.simple-pack.create_plugin_widget" in tools
    assert tools["local.simple-pack.create_plugin_widget"]["annotations"]["readOnlyHint"] is False
    assert (
        tools["local.simple-pack.create_plugin_widget"]["inputSchema"]["properties"]["execute"]["default"]
        is False
    )


def test_server_tool_list_includes_enabled_extension_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(SIMPLE_PACK)
    enable_extension("local.simple-pack")

    names = {tool["name"] for tool in list_tool_schemas()}

    assert "local.simple-pack.create_plugin_widget" in names
    assert "create_text" in names


def test_enabled_extension_tool_call_returns_safe_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(SIMPLE_PACK)
    enable_extension("local.simple-pack")

    result = call_tool(
        "local.simple-pack.create_plugin_widget",
        {
            "profile": "cliente2",
            "context": "index",
            "parent": "root",
            "label": "Teste Extension Pack",
            "execute": False,
        },
    )

    assert result["ok"] is True
    assert result["tool"] == "local.simple-pack.create_plugin_widget"
    assert result["extension_id"] == "local.simple-pack"
    assert result["mode"] == "preview"
    assert result["execute"] is False
    assert result["template"]["kind"] == "appeditor_write"


def test_extension_call_dispatcher_previews_enabled_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(SIMPLE_PACK)
    enable_extension("local.simple-pack")

    result = call_tool(
        "bubble_extension_call",
        {
            "tool": "local.simple-pack.create_plugin_widget",
            "arguments": {
                "profile": "cliente2",
                "context": "index",
                "parent": "root",
                "label": "Teste Extension Pack",
                "execute": False,
            },
        },
    )

    assert result["ok"] is True
    assert result["tool"] == "local.simple-pack.create_plugin_widget"
    assert result["arguments"]["label"] == "Teste Extension Pack"


def test_extension_tool_execute_true_reports_unsupported_runner(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(SIMPLE_PACK)
    enable_extension("local.simple-pack")

    result = call_tool(
        "bubble_extension_call",
        {
            "tool": "local.simple-pack.create_plugin_widget",
            "arguments": {
                "profile": "cliente2",
                "context": "index",
                "parent": "root",
                "label": "Teste Extension Pack",
                "execute": True,
            },
        },
    )

    assert result["ok"] is False
    assert result["error"] == "extension_tool_execution_not_implemented"
    assert result["execute"] is True


def test_generated_api_connector_extension_tool_previews_and_executes(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_session(
        "client",
        session_from_payload(
            {
                "app_id": "synthetic-app",
                "app_version": "test",
                "headers": {"cookie": "sid=test"},
                "source": "unit-test",
            }
        ),
    )
    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )
    append_capture_to_authoring_session(
        session.id,
        Path("tests/fixtures/tool-authoring/api-connector-write-capture.json"),
    )
    extension_id = "local.toolwiz.api_connector.test"
    append_learning_record(
        scope="extension",
        key="api_connector.initialize_call_response_time_ms",
        value={
            "payload": {
                "appname": "courselaunch",
                "app_version": "test",
                "changes": [
                    {
                        "body": 906,
                        "path_array": [
                            "settings",
                            "client_safe",
                            "apiconnector2",
                            "bYRvD",
                            "calls",
                            "beQUv",
                            "response_time_ms",
                        ],
                        "intent": {"name": "ChangeAppSetting"},
                        "version_control_api_version": 4,
                        "changelog_data": [],
                        "session_id": "1783362247423x32",
                    }
                ],
            }
        },
        source="user_declared",
        confidence="confirmed",
        extension_id=extension_id,
    )
    generated = generate_authoring_extension_pack(
        session.id,
        extension_id=extension_id,
        tool_name="local.toolwiz.api_connector.test.create_api_connector_resource",
    )
    assert generated["ok"] is True
    import_extension(Path(str(generated["pack_path"])))
    enable_extension(str(generated["extension_id"]))

    arguments = {
        "profile": "client",
        "execute": False,
        "name": "Dry Run API Connector Test",
        "method": "POST",
        "url": "https://example.com/api/test",
        "headers": {"accept": "application/json"},
        "body": '{"key1": <key1>, "key2": <key2>}',
        "body_params": {"key1": "texto", "key2": 10},
        "initialize": True,
        "response_time_ms": 906,
    }
    preview = call_tool(
        "bubble_extension_call",
        {"tool": str(generated["tool_name"]), "arguments": arguments},
    )

    assert preview["ok"] is True
    assert preview["mode"] == "preview"
    assert preview["execute"] is False
    assert preview["runner"] == "api_connector_resource_v1"
    assert preview["schema"]["inputSchema"]["properties"]["response_time_ms"]["type"] == "integer"
    assert preview["compiled_payload"]["appname"] == "synthetic-app"
    preview_changes = preview["compiled_payload"]["changes"]
    assert any(change.get("intent", {}).get("name") == "CreateApiCall" for change in preview_changes)
    assert any(change.get("path_array", [])[-1:] == ["should_reinitialize"] for change in preview_changes)
    assert any(
        change.get("path_array", [])[-1:] == ["response_time_ms"] and change.get("body") == 906
        for change in preview_changes
    )

    write_calls: list[tuple[dict[str, object], object, bool]] = []

    def fake_write(self, payload, session_data, *, dry_run=False):  # noqa: ANN001
        write_calls.append((payload, session_data, dry_run))
        return {
            "ok": True,
            "request": {"payload": payload},
            "response": {"status": "ok", "last_change": 123},
        }

    monkeypatch.setattr("bubble_mcp.extensions.tools.BubbleEditorClient.write", fake_write)
    executed = call_tool(
        "bubble_extension_call",
        {
            "tool": str(generated["tool_name"]),
            "arguments": {**arguments, "execute": True},
        },
    )

    assert executed["ok"] is True
    assert executed["mode"] == "executed"
    assert executed["execute"] is True
    assert executed["runner"] == "api_connector_resource_v1"
    assert write_calls
    payload, session_data, dry_run = write_calls[0]
    assert dry_run is False
    assert session_data.app_id == "synthetic-app"
    assert payload["appname"] == "synthetic-app"
    payload_changes = payload["changes"]
    assert any("apiconnector2" in change.get("path_array", []) for change in payload_changes)
    assert any(change.get("body") == '{"key1": <key1>, "key2": <key2>}' for change in payload_changes)
    assert any(
        isinstance(change.get("body"), dict) and change["body"].get("%k") == "accept"
        for change in payload_changes
    )
    assert any(
        isinstance(change.get("body"), dict) and change["body"].get("%k") == "key2"
        for change in payload_changes
    )
    assert any(
        change.get("path_array", [])[-1:] == ["response_time_ms"] and change.get("body") == 906
        for change in payload_changes
    )


def test_trigger_custom_event_extension_tool_previews_and_executes(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    save_session(
        "client",
        session_from_payload(
            {
                "app_id": "synthetic-app",
                "app_version": "test",
                "headers": {"cookie": "sid=test"},
                "source": "unit-test",
            }
        ),
    )
    pack_path = tmp_path / "trigger-pack"
    tools_path = pack_path / "tools"
    tools_path.mkdir(parents=True)
    (pack_path / "extension.json").write_text(
        json.dumps(
            {
                "id": "local.trigger-test",
                "name": "Local Trigger Test",
                "version": "0.1.0",
                "bubbleMcpVersion": ">=0.1.0",
                "capabilities": ["tools"],
                "risk": "mutating",
                "author": "unit-test",
                "exports": {"tools": ["tools/trigger-custom-event.tool.json"], "skills": [], "evals": []},
            }
        ),
        encoding="utf-8",
    )
    (tools_path / "trigger-custom-event.tool.json").write_text(
        json.dumps(
            {
                "name": "local.trigger-test.trigger_custom_event",
                "description": "Trigger a Bubble custom event from a workflow using a captured write runner.",
                "risk": "mutating",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "profile": {"type": "string", "description": "Local Bubble MCP profile."},
                        "arguments": {"type": "object", "description": "Custom event argument values."},
                        "execute": {
                            "type": "boolean",
                            "description": "Execute the write after preview and validation.",
                            "default": False,
                        },
                    },
                    "required": ["profile"],
                },
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "idempotentHint": False,
                    "openWorldHint": True,
                },
                "template": {
                    "kind": "appeditor_write",
                    "family": "workflow custom event trigger",
                    "requiresValidation": True,
                    "runner": "trigger_custom_event_v1",
                    "defaults": {
                        "action_index": "1",
                        "custom_event_id": "cmMdG",
                        "event_id": "bi6yt",
                        "existing_action_id": "bdHu5",
                        "existing_action_index": "0",
                        "existing_action_type": "ShowElement",
                        "existing_element_id": "bnSIJ",
                        "id_counter": 20000318,
                        "page_id": "bO9uq",
                        "param_ids": {"user": "cmMdN", "number": "cmMdO"},
                        "workflow_key": "bDfYE",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    validation = validate_extension_pack(pack_path)
    assert validation.ok is True
    import_extension(pack_path)
    enable_extension("local.trigger-test")

    arguments = {
        "profile": "client",
        "execute": False,
        "arguments": {"user": "current user", "number": 1},
    }
    preview = call_tool(
        "bubble_extension_call",
        {"tool": "local.trigger-test.trigger_custom_event", "arguments": arguments},
    )

    assert preview["ok"] is True
    assert preview["mode"] == "preview"
    assert preview["runner"] == "trigger_custom_event_v1"
    assert preview["compiled_payload"]["appname"] == "synthetic-app"
    preview_changes = preview["compiled_payload"]["changes"]
    create_action = next(change for change in preview_changes if change.get("intent", {}).get("name") == "CreateAction")
    action_body = create_action["body"]["1"]
    assert action_body["%x"] == "TriggerCustomEvent"
    assert action_body["%p"]["custom_event"] == "cmMdG"
    assert action_body["%p"]["arguments"]["0"]["arg_value"]["%x"] == "CurrentUser"
    assert action_body["%p"]["arguments"]["1"]["arg_value"] == 1

    write_calls: list[tuple[dict[str, object], object, bool]] = []

    def fake_write(self, payload, session_data, *, dry_run=False):  # noqa: ANN001
        write_calls.append((payload, session_data, dry_run))
        return {
            "ok": True,
            "request": {"payload": payload},
            "response": {"status": "ok", "last_change": 456},
        }

    monkeypatch.setattr("bubble_mcp.extensions.tools.BubbleEditorClient.write", fake_write)
    executed = call_tool(
        "bubble_extension_call",
        {
            "tool": "local.trigger-test.trigger_custom_event",
            "arguments": {**arguments, "execute": True},
        },
    )

    assert executed["ok"] is True
    assert executed["mode"] == "executed"
    assert executed["runner"] == "trigger_custom_event_v1"
    assert write_calls
    payload, session_data, dry_run = write_calls[0]
    assert dry_run is False
    assert session_data.app_id == "synthetic-app"
    assert payload["appname"] == "synthetic-app"
    assert any(change.get("path_array", []) == ["_index", "issues_list", "bi6yt"] for change in payload["changes"])


def test_extension_tool_preview_validates_required_arguments(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(SIMPLE_PACK)
    enable_extension("local.simple-pack")

    result = call_tool(
        "bubble_extension_call",
        {
            "tool": "local.simple-pack.create_plugin_widget",
            "arguments": {"profile": "cliente2", "context": "index", "execute": False},
        },
    )

    assert result["ok"] is False
    assert result["error"] == "extension_tool_missing_required_arguments"
    assert result["missing"] == ["parent", "label"]


def test_extension_collision_is_rejected(tmp_path) -> None:
    report = validate_extension_pack(Path("tests/fixtures/extensions/collision-pack"))

    assert report.ok is False
    assert any("collides with existing tool" in error for error in report.errors)


def test_extension_secret_is_rejected() -> None:
    report = validate_extension_pack(Path("tests/fixtures/extensions/secret-pack"))

    assert report.ok is False
    assert any("possible secret" in error for error in report.errors)


def test_extension_validate_rejects_unsafe_manifest_id(tmp_path) -> None:
    unsafe_pack = tmp_path / "unsafe-id-pack"
    shutil.copytree(SIMPLE_PACK, unsafe_pack)
    manifest = json.loads((unsafe_pack / "extension.json").read_text(encoding="utf-8"))
    manifest["id"] = "../unsafe-pack"
    (unsafe_pack / "extension.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_extension_pack(unsafe_pack)

    assert report.ok is False
    assert any("safe path segment" in error for error in report.errors)


def test_extension_validate_rejects_malformed_tool_input_schema(tmp_path) -> None:
    malformed_pack = tmp_path / "malformed-schema-pack"
    shutil.copytree(SIMPLE_PACK, malformed_pack)
    tool_path = malformed_pack / "tools" / "create-plugin-widget.tool.json"
    tool = json.loads(tool_path.read_text(encoding="utf-8"))
    tool["inputSchema"] = {"type": "string", "properties": [], "required": ["label"]}
    tool_path.write_text(json.dumps(tool), encoding="utf-8")

    report = validate_extension_pack(malformed_pack)

    assert report.ok is False
    assert any("inputSchema.type must be object" in error for error in report.errors)
    assert any("inputSchema.properties must be an object" in error for error in report.errors)


def test_extension_validate_rejects_mutating_tool_without_execute_default_false(tmp_path) -> None:
    malformed_pack = tmp_path / "unsafe-execute-pack"
    shutil.copytree(SIMPLE_PACK, malformed_pack)
    tool_path = malformed_pack / "tools" / "create-plugin-widget.tool.json"
    tool = json.loads(tool_path.read_text(encoding="utf-8"))
    del tool["inputSchema"]["properties"]["execute"]
    tool_path.write_text(json.dumps(tool), encoding="utf-8")

    report = validate_extension_pack(malformed_pack)

    assert report.ok is False
    assert any("mutating tools require boolean execute input" in error for error in report.errors)


def test_malformed_installed_extension_does_not_crash_tool_list(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    pack_path = tmp_path / "extensions" / "packs" / "local.malformed-pack"
    pack_path.mkdir(parents=True)
    (pack_path / "extension.json").write_text("{not-json", encoding="utf-8")
    (pack_path / "state.json").write_text(
        json.dumps({"state": "enabled"}),
        encoding="utf-8",
    )

    names = {tool["name"] for tool in list_tool_schemas()}

    assert "create_text" in names
    assert "local.malformed-pack.create_plugin_widget" not in names


def test_duplicate_extension_tool_names_are_filtered(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    duplicate_pack = tmp_path / "duplicate-pack"
    shutil.copytree(SIMPLE_PACK, duplicate_pack)
    manifest = json.loads((duplicate_pack / "extension.json").read_text(encoding="utf-8"))
    manifest["id"] = "local.duplicate-pack"
    manifest["name"] = "Duplicate Pack"
    (duplicate_pack / "extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    import_extension(SIMPLE_PACK)
    import_extension(duplicate_pack)
    enable_extension("local.simple-pack")
    enable_extension("local.duplicate-pack")

    names = [tool["name"] for tool in enabled_extension_tool_schemas()]

    assert names.count("local.simple-pack.create_plugin_widget") == 1


def test_secret_like_property_name_without_secret_value_is_allowed(tmp_path) -> None:
    harmless_pack = tmp_path / "harmless-secret-name-pack"
    shutil.copytree(SIMPLE_PACK, harmless_pack)
    tool_path = harmless_pack / "tools" / "create-plugin-widget.tool.json"
    tool = json.loads(tool_path.read_text(encoding="utf-8"))
    properties = tool["inputSchema"]["properties"]
    properties["api_key"] = {
        "type": "string",
        "description": "Optional key name supplied by the user at runtime.",
    }
    tool_path.write_text(json.dumps(tool), encoding="utf-8")

    report = validate_extension_pack(harmless_pack)

    assert report.ok is True
