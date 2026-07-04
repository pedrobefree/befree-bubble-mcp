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
        "tool_property_descriptions",
        "tool_annotations",
        "resources",
        "resource_templates",
        "prompts",
        "runtime_coverage",
    }


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
