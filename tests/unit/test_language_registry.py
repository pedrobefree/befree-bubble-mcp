from bubble_mcp.language.registry import build_language_index
from bubble_mcp.language.query import language_query, language_tool_detail
from bubble_mcp.language.diff import language_diff, save_language_snapshot
from bubble_mcp.language.framework_pack import framework_language_pack
from bubble_mcp.language.compiler import compile_framework_program


def test_language_index_is_compact_versioned_and_counts_dynamic_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = build_language_index(profile="cliente2")

    assert result["ok"] is True
    assert result["language"] == "bubble-mcp"
    assert result["detail"] == "index"
    assert result["registry_version"].startswith("sha256:")
    assert result["counts"]["tools"] > 250
    assert "visual_editor" in result["families"]
    assert result["runtime_rules_digest"]
    assert "bubble_language_query" in result["entrypoints"]
    assert isinstance(result["skills_digest"], list)
    assert "tools" not in result


def test_language_query_returns_scoped_compact_matches_without_full_schema(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = language_query(query="create checkout button", families=["visual_editor"], limit=8)

    assert result["ok"] is True
    assert result["detail"] == "compact"
    assert result["matches"]
    assert len(result["matches"]) <= 8
    assert any(match["name"] == "create_button" for match in result["matches"])
    assert all(match["family"] == "visual_editor" for match in result["matches"])
    button = next(match for match in result["matches"] if match["name"] == "create_button")
    assert button["capabilities"]["supports_preview"] is True
    assert button["capabilities"]["requires_approval"] is True
    assert button["status"]["state"] == "available"
    assert all("inputSchema" not in match for match in result["matches"])


def test_language_tool_detail_lazy_loads_selected_schemas_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = language_tool_detail(["create_button", "bubble_context_find"], detail="full")

    assert result["ok"] is True
    assert [tool["name"] for tool in result["tools"]] == ["create_button", "bubble_context_find"]
    assert all("inputSchema" in tool for tool in result["tools"])


def test_language_diff_reports_added_changed_removed_entries(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    old = {
        "registry_version": "sha256:old",
        "entries": [
            {"name": "create_button", "schema_hash": "a", "family": "visual_editor"},
            {"name": "removed_tool", "schema_hash": "r", "family": "custom"},
        ],
    }
    new = {
        "registry_version": "sha256:new",
        "entries": [
            {"name": "create_button", "schema_hash": "b", "family": "visual_editor"},
            {"name": "new_tool", "schema_hash": "n", "family": "extension"},
        ],
    }

    save_language_snapshot(old)
    save_language_snapshot(new)
    result = language_diff(since="sha256:old", current="sha256:new")

    assert result["ok"] is True
    assert result["added"] == ["new_tool"]
    assert result["changed"] == ["create_button"]
    assert result["removed"] == ["removed_tool"]


def test_framework_language_pack_filters_context_for_framework_and_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = framework_language_pack(
        framework="bmad",
        profile="cliente2",
        scope="create checkout page with button and workflow",
        max_tools=10,
    )

    assert result["ok"] is True
    assert result["framework"] == "bmad"
    assert result["registry_version"].startswith("sha256:")
    assert result["language_index"]["counts"]["tools"] > 250
    assert result["runtime_rules"]
    assert result["tool_matches"]
    assert len(result["tool_matches"]) <= 10
    assert "full_catalog" not in result


def test_compile_framework_program_outputs_preview_safe_calls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="superpowers",
        profile="cliente2",
        program={
            "objective": "Create checkout CTA",
            "steps": [
                {"intent": "resolve_context", "query": "page checkout"},
                {
                    "tool": "create_group",
                    "arguments": {"context": "checkout", "parent": "root", "name": "Checkout section"},
                },
                {
                    "tool": "create_button",
                    "arguments": {
                        "context": "checkout",
                        "parent": "<created_group_id>",
                        "label": "Start checkout",
                    },
                },
            ],
        },
    )

    assert result["ok"] is True
    assert result["mode"] == "preview"
    assert result["approval_required"] is True
    assert [call["tool"] for call in result["compiled_calls"]] == [
        "bubble_context_find",
        "create_group",
        "create_button",
    ]
    assert result["compiled_calls"][1]["arguments"]["execute"] is False
    assert result["compiled_calls"][2]["arguments"]["profile"] == "cliente2"
    assert result["validation_plan"]


def test_compile_framework_program_maps_common_intents_to_preview_safe_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Create a compact login form",
            "steps": [
                {
                    "intent": "create_container",
                    "context": "login",
                    "parent": "root",
                    "label": "Login form",
                },
                {
                    "intent": "headline",
                    "context": "login",
                    "parent": "<group>",
                    "text": "Welcome back",
                },
                {
                    "intent": "cta_button",
                    "context": "login",
                    "parent": "<group>",
                    "text": "Continue",
                },
                {
                    "intent": "sync_evidence",
                    "evidence": {"preview": "compiled"},
                },
            ],
        },
    )

    assert result["ok"] is True
    assert [call["tool"] for call in result["compiled_calls"]] == [
        "create_group",
        "create_text",
        "create_button",
        "bubble_framework_sync_evidence",
    ]
    assert result["compiled_calls"][0]["arguments"]["name"] == "Login form"
    assert result["compiled_calls"][1]["arguments"]["content"] == "Welcome back"
    assert result["compiled_calls"][2]["arguments"]["label"] == "Continue"
    assert result["compiled_calls"][2]["arguments"]["execute"] is False
    assert "execute" not in result["compiled_calls"][3]["arguments"]
    assert result["compiled_calls"][3]["arguments"]["framework"] == "bmad"


def test_compile_framework_program_reports_missing_required_arguments(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="sdd",
        profile="cliente2",
        program={
            "objective": "Incomplete button",
            "steps": [{"intent": "create_button", "context": "home", "text": "Save"}],
        },
    )

    assert result["ok"] is False
    assert result["error"] == "framework_program_missing_required_arguments"
    assert result["missing_arguments"] == [
        {
            "step": 1,
            "tool": "create_button",
            "missing": ["parent"],
            "required": ["profile", "context", "parent", "label"],
        }
    ]


def test_compile_framework_program_rejects_unknown_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="bmad",
        profile="cliente2",
        program={"objective": "Bad", "steps": [{"tool": "missing_tool", "arguments": {}}]},
    )

    assert result["ok"] is False
    assert result["error"] == "framework_program_has_unavailable_tools"
    assert result["unavailable_tools"] == ["missing_tool"]
