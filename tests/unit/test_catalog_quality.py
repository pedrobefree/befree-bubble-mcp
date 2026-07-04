from bubble_mcp.catalog_quality import catalog_quality_report


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
        "tool_property_descriptions",
        "tool_annotations",
        "resources",
        "resource_templates",
        "prompts",
        "runtime_coverage",
    }
