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


def test_search_context_exact_matches_only_identifiers_or_labels() -> None:
    context = load_context(FIXTURE)

    assert search_context(context, "user email", exact=True) == []

    results = search_context(context, "datatype:user", exact=True)

    assert results == [
        {
            "id": "datatype:user",
            "label": "User",
            "type": "data_type",
            "score": 1,
            "match": "exact",
            "metadata": {"fields": "email, name"},
        }
    ]


def test_search_context_can_omit_metadata_for_compact_agent_checks() -> None:
    context = load_context(FIXTURE)

    results = search_context(context, "datatype:user", exact=True, include_metadata=False)

    assert results == [
        {
            "id": "datatype:user",
            "label": "User",
            "type": "data_type",
            "score": 1,
            "match": "exact",
        }
    ]


def test_context_neighbors_returns_related_nodes() -> None:
    context = load_context(FIXTURE)

    neighbors = context_neighbors(context, "page:index")

    assert neighbors["neighbors"][0].id == "reusable:header"
