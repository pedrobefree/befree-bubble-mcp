import json
import shutil
from pathlib import Path

from bubble_mcp.extensions.store import enable_extension, import_extension
from bubble_mcp.extensions.tools import enabled_extension_tool_schemas
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.server.tools import call_tool


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
