import json
import os
from pathlib import Path
import subprocess
import sys

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
    cases = load_ambiguity_cases()
    missing_expected = [dict(case) for case in cases]
    missing_expected[0]["id"] = "missing-tools"
    missing_expected[0]["expected_tool"] = "missing_tool"
    with pytest.raises(ValueError, match="missing-tools: unknown expected tool missing_tool"):
        catalog_ambiguity_report(cases=missing_expected)

    missing_contrast = [dict(case) for case in cases]
    missing_contrast[0]["id"] = "contrast-tools"
    missing_contrast[0]["contrast_tools"] = ["missing_tool"]
    with pytest.raises(ValueError, match="contrast-tools: unknown contrast tools missing_tool"):
        catalog_ambiguity_report(cases=missing_contrast)


def test_ambiguity_report_rejects_empty_or_reduced_corpus() -> None:
    with pytest.raises(ValueError, match="must contain exactly 27 cases; got 0"):
        catalog_ambiguity_report(cases=[])

    reduced = load_ambiguity_cases()[:-1]
    with pytest.raises(ValueError, match="must contain exactly 27 cases; got 26"):
        catalog_ambiguity_report(cases=reduced)


def test_ambiguity_report_rejects_missing_family_at_full_case_count() -> None:
    cases = [dict(case) for case in load_ambiguity_cases()]
    for case in cases:
        if case["family"] == "html_import":
            case["family"] = "workflow"

    with pytest.raises(ValueError, match=r"missing=\['html_import'\], extra=\[\]"):
        catalog_ambiguity_report(cases=cases)


def test_ambiguity_report_names_missing_expected_schema() -> None:
    schemas = [schema for schema in list_tool_schemas() if schema["name"] != "create_event"]

    report = catalog_ambiguity_report(schemas)

    assert report["ok"] is False
    failure = next(
        failure
        for failure in report["failures"]
        if failure["case_id"] == "workflow.create_event"
    )
    assert {
        "failure_type": "missing_schema",
        "family": "workflow",
        "expected_tool": "create_event",
        "actual_tool": "",
    }.items() <= failure.items()


def test_ambiguity_report_names_required_argument_contract_drift() -> None:
    schemas = [dict(schema) for schema in list_tool_schemas()]
    create_event = next(schema for schema in schemas if schema["name"] == "create_event")
    input_schema = dict(create_event["inputSchema"])
    input_schema["required"] = ["profile"]
    create_event["inputSchema"] = input_schema

    report = catalog_ambiguity_report(schemas)

    failure = next(
        failure
        for failure in report["failures"]
        if failure["case_id"] == "workflow.create_event"
    )
    assert {
        "failure_type": "contract_mismatch",
        "expected_tool": "create_event",
        "essential_args": ["context", "event_type", "profile"],
        "actual_required": ["profile"],
    }.items() <= failure.items()


def test_ambiguity_audit_runs_from_checkout_without_pythonpath() -> None:
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "scripts/audit_catalog_ambiguity.py"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["summary"]["case_count"] == 27
    assert report["summary"]["family_count"] == 8
