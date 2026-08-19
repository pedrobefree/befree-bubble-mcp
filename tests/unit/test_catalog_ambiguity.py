import json
from pathlib import Path

import pytest

from bubble_mcp.harness.catalog_ambiguity import (
    catalog_ambiguity_report,
    load_ambiguity_cases,
)
from bubble_mcp.server.schemas import list_tool_schemas


def test_catalog_ambiguity_matrix_passes_all_required_families() -> None:
    report = catalog_ambiguity_report()

    assert report["ok"] is True
    assert report["summary"] == {
        "case_count": 27,
        "family_count": 8,
        "canonical_ok": 27,
        "reversed_ok": 27,
        "rotated_ok": 27,
        "order_independent": 27,
        "failed_cases": 0,
    }
    assert report["failures"] == []


def test_ambiguity_report_is_identical_for_reversed_schema_input() -> None:
    schemas = list_tool_schemas()

    assert catalog_ambiguity_report(schemas) == catalog_ambiguity_report(reversed(schemas))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            [
                {
                    "id": "duplicate",
                    "family": "workflow",
                    "query": "first query",
                    "expected_tool": "create_event",
                    "contrast_tools": ["create_workflow"],
                },
                {
                    "id": "duplicate",
                    "family": "workflow",
                    "query": "second query",
                    "expected_tool": "create_event",
                    "contrast_tools": ["create_workflow"],
                },
            ],
            "duplicate case id: duplicate",
        ),
        (
            [
                {
                    "id": "one",
                    "family": "workflow",
                    "query": "same query",
                    "expected_tool": "create_event",
                    "contrast_tools": ["create_workflow"],
                },
                {
                    "id": "two",
                    "family": "workflow",
                    "query": "same query",
                    "expected_tool": "create_workflow",
                    "contrast_tools": ["create_event"],
                },
            ],
            "duplicate query in case two",
        ),
        (
            [
                {
                    "id": "bad-family",
                    "family": "unknown",
                    "query": "a query",
                    "expected_tool": "create_event",
                    "contrast_tools": ["create_workflow"],
                }
            ],
            "bad-family: unknown family unknown",
        ),
        (
            [
                {
                    "id": "no-contrast",
                    "family": "workflow",
                    "query": "a query",
                    "expected_tool": "create_event",
                    "contrast_tools": [],
                }
            ],
            "no-contrast: contrast_tools must be a non-empty list",
        ),
        (
            [
                {
                    "id": "self-contrast",
                    "family": "workflow",
                    "query": "a query",
                    "expected_tool": "create_event",
                    "contrast_tools": ["create_event"],
                }
            ],
            "self-contrast: expected tool cannot be a contrast tool",
        ),
    ],
)
def test_ambiguity_loader_rejects_invalid_cases(
    tmp_path: Path,
    payload: list[dict[str, object]],
    message: str,
) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_ambiguity_cases(path)


def test_ambiguity_report_rejects_unknown_expected_and_contrast_tools() -> None:
    with pytest.raises(ValueError, match="missing-tools: unknown expected tool missing_tool"):
        catalog_ambiguity_report(
            cases=[
                {
                    "id": "missing-tools",
                    "family": "workflow",
                    "query": "create an event",
                    "expected_tool": "missing_tool",
                    "contrast_tools": ["also_missing"],
                }
            ]
        )

    with pytest.raises(ValueError, match="contrast-tools: unknown contrast tools missing_tool"):
        catalog_ambiguity_report(
            cases=[
                {
                    "id": "contrast-tools",
                    "family": "workflow",
                    "query": "create an event",
                    "expected_tool": "create_event",
                    "contrast_tools": ["missing_tool"],
                }
            ]
        )
