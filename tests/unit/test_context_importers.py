import json
from pathlib import Path

from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.context.importers import import_context_artifact
from bubble_mcp.context.queries import search_context
from bubble_mcp.context.source import load_context, save_context


FIXTURE = Path("tests/fixtures/context/synthetic-crawler-public.json")


def test_import_crawler_index_builds_context_graph(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context = import_context_artifact(FIXTURE)

    assert context.app_id == "synthetic-app"
    assert context.summary()["counts"]["page"] == 1
    assert context.summary()["counts"]["element"] == 2
    assert search_context(context, "Welcome")[0]["label"] == "Title"

    out = tmp_path / "context.json"
    save_context(context, out)
    assert load_context(out).summary()["nodes"] == context.summary()["nodes"]


def test_compiler_uses_imported_context_paths() -> None:
    context = import_context_artifact(FIXTURE)
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_text",
                "args": {"context": "index", "parent": "Card", "content": "Nested"},
            }
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app", context=context)
    payload = compiled["steps"][0]["args"]["write_payload"]

    assert payload["changes"][0]["path_array"] == ["%p3", "pgIndex", "%el", "elCard"]


def test_import_bubble_like_export(tmp_path) -> None:  # type: ignore[no-untyped-def]
    export_path = tmp_path / "app.bubble.json"
    export_path.write_text(
        json.dumps(
            {
                "appname": "synthetic-app",
                "pages": {
                    "pgIndex": {
                        "%p": {"%nm": "index"},
                        "%el": {"elText": {"%x": "Text", "%p": {"%nm": "Headline"}}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    context = import_context_artifact(export_path, kind="bubble")

    assert context.summary()["counts"]["page"] == 1
    assert search_context(context, "Headline")[0]["type"] == "element"
