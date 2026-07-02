import json
from pathlib import Path

from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.source import load_context
from bubble_mcp.sessions.store import save_session, session_from_payload


def test_detect_context_imports_local_bubble_file(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    bubble_file = tmp_path / "app.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "appname": "synthetic-app",
                "pages": {
                    "pgIndex": {
                        "id": "rootIndex",
                        "%p": {"%nm": "index"},
                        "%el": {"elTitle": {"%x": "Text", "%p": {"%nm": "Title"}}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = detect_project_context(profile="dev", app_id="synthetic-app", bubble_file=bubble_file)

    assert result.ok is True
    assert result.source == "bubble_file"
    context = load_context(result.context_path)
    page = next(node for node in context.nodes if node.type == "page")
    assert page.metadata["bubble_id"] == "pgIndex"
    assert page.metadata["root_id"] == "rootIndex"
    assert page.metadata["children"] == ["elTitle"]


def test_detect_context_uses_cached_compact_context(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    first_source = tmp_path / "app.bubble"
    first_source.write_text(
        json.dumps({"appname": "synthetic-app", "pages": {"pgIndex": {"%p": {"%nm": "index"}}}}),
        encoding="utf-8",
    )

    first = detect_project_context(profile="dev", app_id="synthetic-app", bubble_file=first_source)
    second = detect_project_context(profile="dev", app_id="synthetic-app")

    assert second.source == "cached_context"
    assert second.context_path == first.context_path


def test_detect_context_extracts_consolelog_app_file(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    consolelog_file = tmp_path / "console.txt"
    consolelog_file.write_text(
        'console.log(app) {"appname":"synthetic-app","pages":{"pgIndex":{"%p":{"%nm":"index"}}}}',
        encoding="utf-8",
    )

    result = detect_project_context(
        profile="dev",
        app_id="synthetic-app",
        consolelog_file=consolelog_file,
    )

    assert result.source == "consolelog_file"
    assert load_context(result.context_path).summary()["counts"]["page"] == 1


def test_detect_context_falls_back_to_editor_crawler(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    session = session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}})
    save_session("dev", session)

    def fake_crawl(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "appId": "synthetic-app",
            "pages": [
                {
                    "id": "pgIndex",
                    "name": "index",
                    "rootId": "rootIndex",
                    "elements": {"elTitle": {"%x": "Text", "%p": {"%nm": "Title"}}},
                    "workflows": {},
                }
            ],
            "reusables": [],
            "backendWorkflows": [],
            "pageIndex": {"index": "pgIndex"},
            "reusableIndex": {},
            "apiIndex": {},
            "idToPath": {"elTitle": "%p3.pgIndex.%el.elTitle"},
            "source": "full_crawl",
        }

    monkeypatch.setattr("bubble_mcp.context.detector.crawl_project_index", fake_crawl)

    result = detect_project_context(profile="dev", app_id="synthetic-app", force=True)

    assert result.source == "editor_crawler"
    assert result.crawler_index_path is not None
    assert Path(result.crawler_index_path).exists()
    context = load_context(result.context_path)
    assert any(node.metadata.get("path_array") == ["%p3", "pgIndex", "%el", "elTitle"] for node in context.nodes)
