from bubble_mcp.language.registry import build_language_index
from bubble_mcp.language.query import language_query, language_tool_detail
from bubble_mcp.language.diff import language_diff, save_language_snapshot


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
