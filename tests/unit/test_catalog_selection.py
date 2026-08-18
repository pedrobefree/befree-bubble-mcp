from bubble_mcp.harness.catalog_selection import catalog_selection_report
from bubble_mcp.server.schemas import list_tool_schemas


def test_every_mcp_tool_has_passing_deterministic_selection_evidence() -> None:
    report = catalog_selection_report()

    assert report["ok"] is True
    assert report["summary"] == {
        "tool_count": 327,
        "case_count": 327,
        "canonical_ok": 327,
        "reordered_ok": 327,
        "order_independent": 327,
        "missing_cases": 0,
        "failed_cases": 0,
    }
    assert report["failures"] == []
    assert all(result["case_id"].startswith("catalog.exact.") for result in report["results"])


def test_selection_report_is_identical_for_reversed_schema_input() -> None:
    schemas = list_tool_schemas()

    assert catalog_selection_report(schemas) == catalog_selection_report(list(reversed(schemas)))


def test_selection_report_rejects_a_missing_candidate_schema() -> None:
    schemas = [schema for schema in list_tool_schemas() if schema["name"] != "create_text"]

    report = catalog_selection_report(schemas)

    assert report["ok"] is False
    assert report["summary"]["tool_count"] == 327
    assert report["summary"]["case_count"] == 327
    failure = next(
        failure
        for failure in report["failures"]
        if failure.get("failure_type") == "missing_schema"
    )
    assert {
        "case_id": "catalog.schema.missing.create_text",
        "failure_type": "missing_schema",
        "expected_tool": "create_text",
    }.items() <= failure.items()


def test_selection_report_rejects_changed_candidate_required_args() -> None:
    schemas = [dict(schema) for schema in list_tool_schemas()]
    create_text = next(schema for schema in schemas if schema["name"] == "create_text")
    input_schema = dict(create_text["inputSchema"])
    input_schema["required"] = ["profile"]
    create_text["inputSchema"] = input_schema

    report = catalog_selection_report(schemas)

    assert report["ok"] is False
    failure = next(
        failure
        for failure in report["failures"]
        if failure.get("failure_type") == "contract_mismatch"
        and failure.get("expected_tool") == "create_text"
    )
    assert {
        "case_id": "catalog.schema.contract.create_text",
        "failure_type": "contract_mismatch",
        "expected_tool": "create_text",
        "essential_args": ["content", "context", "parent", "profile"],
        "actual_required": ["profile"],
    }.items() <= failure.items()


def test_selection_failure_names_case_expected_and_actual_tool(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import bubble_mcp.harness.catalog_selection as selection

    real_search = selection.search_tool_catalog

    def wrong_create_text(query, **kwargs):  # type: ignore[no-untyped-def]
        if query == "create_text":
            return {"matches": [{"name": "create_button", "required": []}]}
        return real_search(query, **kwargs)

    monkeypatch.setattr(selection, "search_tool_catalog", wrong_create_text)

    report = catalog_selection_report()

    assert report["ok"] is False
    assert any(
        {"case_id", "expected_tool", "actual_tool", "essential_args"} <= failure.keys()
        for failure in report["failures"]
    )
