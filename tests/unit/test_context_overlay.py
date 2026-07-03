from pathlib import Path

from bubble_mcp.context.freshness import context_freshness, load_context_with_overlay
from bubble_mcp.context.mutation_overlay import record_mutation_overlay
from bubble_mcp.context.source import load_context


FIXTURE = Path("tests/fixtures/context/synthetic-app-context.json")


def test_load_context_with_overlay_adds_pages_and_elements(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    payload = {
        "appname": "synthetic-app",
        "changes": [
            {
                "intent": {"name": "CreatePage"},
                "path_array": ["%p3", "mcp01"],
                "body": {"id": "mcp01", "%nm": "mcp-01"},
            },
            {
                "intent": {"name": "CreateElement"},
                "path_array": ["%p3", "mcp01", "%el", "bText"],
                "body": {"id": "bText", "%x": "Text", "%p": {"%nm": "Title", "%3": "Hello"}},
            },
        ],
    }
    record_mutation_overlay(
        profile="smoke",
        app_id="synthetic-app",
        payload=payload,
        source="pytest",
    )

    context = load_context_with_overlay(FIXTURE, profile="smoke", app_id="synthetic-app")

    assert context.source.endswith("+mutation_overlay")
    assert any(node.id == "page:mcp-01" for node in context.nodes)
    assert any(node.id == "element:bText" for node in context.nodes)
    assert context.metadata["mutation_overlay"]["nodes_added"] == 2


def test_context_freshness_uses_file_mtime_when_metadata_missing() -> None:
    context = load_context(FIXTURE)

    result = context_freshness(context, path=FIXTURE, max_age_hours=24 * 3650)

    assert result["status"] == "fresh"
    assert result["timestamp_source"] == "file_mtime"
