import bubble_mcp.catalog_quality as quality
from bubble_mcp.catalog_quality import _check_tool_schemas, catalog_quality_report


def test_catalog_quality_report_passes_current_catalog() -> None:
    report = catalog_quality_report()

    assert report["ok"] is True
    assert report["summary"]["tool_count"] >= 220
    assert report["summary"]["resource_count"] >= 4
    assert report["summary"]["prompt_count"] >= 3
    assert report["summary"]["issue_count"] == 0
    assert report["issues"] == []
    assert {check["name"] for check in report["checks"]} >= {
        "tool_names",
        "tool_descriptions",
        "tool_input_schemas",
        "legacy_required_fields",
        "tool_property_descriptions",
        "tool_annotations",
        "resources",
        "resource_templates",
        "prompts",
        "runtime_coverage",
        "cli_catalog_parity",
    }


def test_catalog_quality_includes_complete_deterministic_selection_coverage() -> None:
    report = catalog_quality_report()
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["deterministic_selection_coverage"] == {
        "name": "deterministic_selection_coverage",
        "ok": True,
        "issue_count": 0,
    }
    assert report["summary"]["tool_count"] == 327


def test_catalog_quality_includes_deterministic_ambiguity_matrix() -> None:
    report = catalog_quality_report()
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["deterministic_ambiguity_matrix"] == {
        "name": "deterministic_ambiguity_matrix",
        "ok": True,
        "issue_count": 0,
        "case_count": 27,
        "family_count": 8,
    }


def test_ambiguity_check_converts_wrong_tool_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        quality,
        "catalog_ambiguity_report",
        lambda: {
            "ok": False,
            "summary": {"case_count": 1, "family_count": 1},
            "failures": [
                {
                    "case_id": "workflow.create_event",
                    "family": "workflow",
                    "failure_type": "selection_mismatch",
                    "expected_tool": "create_event",
                    "actual_tool": "create_button",
                }
            ],
        },
    )

    check, issues = quality._deterministic_ambiguity_check()

    assert check == {
        "name": "deterministic_ambiguity_matrix",
        "ok": False,
        "issue_count": 1,
        "case_count": 1,
        "family_count": 1,
    }
    assert issues == [
        {
            "check": "deterministic_ambiguity_matrix",
            "scope": "tool",
            "name": "create_event",
            "field": "selection",
            "message": "workflow.create_event: expected create_event, got create_button (selection_mismatch).",
        }
    ]


def test_ambiguity_check_rejects_non_ok_report_without_failures(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        quality,
        "catalog_ambiguity_report",
        lambda: {
            "ok": False,
            "summary": {"case_count": 0, "family_count": 0},
            "failures": [],
        },
    )

    check, issues = quality._deterministic_ambiguity_check()

    assert check["ok"] is False
    assert issues == [
        {
            "check": "deterministic_ambiguity_matrix",
            "scope": "catalog",
            "name": "catalog_ambiguity",
            "field": "selection",
            "message": "Catalog ambiguity report was not ok without convertible failures.",
        }
    ]


def test_deterministic_selection_check_rejects_non_ok_report_without_failures(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        quality,
        "catalog_selection_report",
        lambda: {"ok": False, "summary": {"missing_cases": 1}, "failures": []},
    )

    check, issues = quality._deterministic_selection_check()

    assert check == {
        "name": "deterministic_selection_coverage",
        "ok": False,
        "issue_count": 1,
    }
    assert issues == [
        {
            "check": "deterministic_selection_coverage",
            "scope": "catalog",
            "name": "catalog_selection",
            "field": "selection",
            "message": "Catalog selection report was not ok without convertible failures.",
        }
    ]


def test_deterministic_selection_check_names_extra_candidate_schema(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        quality,
        "catalog_selection_report",
        lambda: {
            "ok": False,
            "summary": {},
            "failures": [
                {
                    "case_id": "catalog.schema.extra.unexpected_tool",
                    "failure_type": "extra_schema",
                    "expected_tool": "",
                    "actual_tool": "unexpected_tool",
                }
            ],
        },
    )

    _, issues = quality._deterministic_selection_check()

    assert issues == [
        {
            "check": "deterministic_selection_coverage",
            "scope": "tool",
            "name": "unexpected_tool",
            "field": "selection",
            "message": "catalog.schema.extra.unexpected_tool: unexpected candidate schema unexpected_tool.",
        }
    ]


def test_catalog_quality_rejects_read_only_description_without_annotation() -> None:
    _, issues = _check_tool_schemas(
        [
            {
                "name": "unsafe_status",
                "description": "Return status metadata. Read-only.",
                "inputSchema": {"type": "object", "properties": {}, "required": []},
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "idempotentHint": False,
                    "openWorldHint": False,
                },
            }
        ]
    )

    assert {
        "check": "tool_annotations",
        "scope": "tool",
        "name": "unsafe_status",
        "field": "annotations.readOnlyHint",
        "message": "Tools described as read-only must set readOnlyHint=true.",
    } in issues
