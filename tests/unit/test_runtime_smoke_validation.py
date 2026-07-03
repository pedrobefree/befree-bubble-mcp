import json
from pathlib import Path

from bubble_mcp.runtime_smoke_validation import validate_execute_write_context


def write_context(path: Path, *, include_button: bool = True) -> None:
    nodes = [
        {
            "id": "page:mcp_smoke_run_1",
            "label": "mcp_smoke_run_1",
            "type": "page",
            "metadata": {"children": ["gp1", "tx1", "bt1", "in1"]},
        },
        {
            "id": "element:gp1",
            "label": "gp1",
            "type": "element",
            "metadata": {
                "bubble_id": "gp1",
                "context": "page:mcp_smoke_run_1",
                "element_type": "Group",
                "properties": {"container_layout": "column", "fit_height": True},
            },
        },
        {
            "id": "element:tx1",
            "label": "tx1",
            "type": "element",
            "metadata": {
                "bubble_id": "tx1",
                "context": "page:mcp_smoke_run_1",
                "element_type": "Text",
                "properties": {
                    "fit_height": True,
                    "text": {"entries": {"0": "Runtime smoke run_1"}},
                },
            },
        },
        {
            "id": "element:in1",
            "label": "in1",
            "type": "element",
            "metadata": {
                "bubble_id": "in1",
                "context": "page:mcp_smoke_run_1",
                "element_type": "Input",
                "properties": {
                    "fixed_height": True,
                    "placeholder": {"entries": {"0": "Runtime smoke"}},
                },
            },
        },
    ]
    if include_button:
        nodes.append(
            {
                "id": "element:bt1",
                "label": "bt1",
                "type": "element",
                "metadata": {
                    "bubble_id": "bt1",
                    "context": "page:mcp_smoke_run_1",
                    "element_type": "Button",
                    "properties": {
                        "fit_width": True,
                        "fit_height": True,
                        "text": {"entries": {"0": "Runtime smoke"}},
                    },
                },
            }
        )
    path.write_text(
        json.dumps({"app_id": "synthetic-app", "source": "test", "nodes": nodes, "edges": []}),
        encoding="utf-8",
    )


def test_validate_execute_write_context_accepts_expected_smoke_objects(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context_file = tmp_path / "context.json"
    write_context(context_file)

    result = validate_execute_write_context(context_file, run_id="run_1")

    assert result["ok"] is True
    assert result["page"] == "mcp_smoke_run_1"
    assert [check["name"] for check in result["checks"]] == [
        "group_defaults",
        "text_defaults",
        "button_defaults",
        "input_defaults",
    ]


def test_validate_execute_write_context_reports_missing_required_object(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context_file = tmp_path / "context.json"
    write_context(context_file, include_button=False)

    result = validate_execute_write_context(context_file, run_id="run_1")

    assert result["ok"] is False
    assert "expected Button" in "\n".join(result["errors"])
