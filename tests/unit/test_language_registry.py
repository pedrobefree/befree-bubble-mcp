from bubble_mcp.language.registry import build_language_index


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
