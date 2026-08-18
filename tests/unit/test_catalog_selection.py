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
