from pathlib import Path

from bubble_mcp.context.queries import context_neighbors, search_context
from bubble_mcp.context.source import load_context


FIXTURE = Path("tests/fixtures/context/synthetic-app-context.json")


def test_load_context_and_summary() -> None:
    context = load_context(FIXTURE)

    assert context.app_id == "synthetic-app"
    assert context.summary()["counts"]["page"] == 1
    assert context.summary()["counts"]["workflow"] == 1


def test_search_context_finds_data_type_by_field() -> None:
    context = load_context(FIXTURE)

    results = search_context(context, "user email")

    assert results[0]["id"] == "datatype:user"


def test_context_neighbors_returns_related_nodes() -> None:
    context = load_context(FIXTURE)

    neighbors = context_neighbors(context, "page:index")

    assert neighbors["neighbors"][0].id == "reusable:header"
