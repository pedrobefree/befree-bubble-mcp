from pathlib import Path

from bubble_mcp.style_import.runtime import (
    build_style_import_plan,
    create_styles_from_html_runtime,
)


def test_build_style_import_plan_returns_preview_candidate_and_operations() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")

    result = build_style_import_plan(
        html,
        profile="smoke",
        selector=".btn-primary",
        style_name_prefix="HTML",
        element_type="Button",
        execute=False,
    )

    assert result["ok"] is True
    assert result["execute"] is False
    assert result["summary"] == {
        "candidate_count": 1,
        "style_count": 1,
        "operation_count": 6,
        "state_count": 4,
        "unsupported_count": 0,
    }
    assert result["candidates"][0]["name"] == "HTML Button Primary"
    assert result["candidates"][0]["base"]["border_width"] == 1
    assert result["candidates"][0]["states"]["hover"]["bg_color"] == "#004eeb"
    assert result["candidates"][0]["states"]["pressed"]["border_color"] == "#00359e"
    assert [operation["tool"] for operation in result["operations"]] == [
        "create_style",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "reorder_style_states",
    ]
    assert result["operations"][0]["arguments"]["dry_run"] is True
    assert result["operations"][1]["arguments"]["condition"] == "hover"


def test_build_style_import_plan_aggregates_mapper_unsupported() -> None:
    result = build_style_import_plan(
        """
        <style>
          .btn-primary {
            background-color: #155eef;
            transform: translateY(-1px);
          }
          .btn-primary:hover {
            filter: brightness(95%);
          }
        </style>
        <button class="btn-primary">Save</button>
        """,
        profile="smoke",
        selector=".btn-primary",
        style_name_prefix="HTML",
        element_type="Button",
        execute=False,
    )

    assert result["summary"]["unsupported_count"] == 2
    assert result["unsupported"] == [
        {"state": "base", "property": "transform", "value": "translateY(-1px)"},
        {"state": "hover", "property": "filter", "value": "brightness(95%)"},
    ]
    assert result["candidates"][0]["unsupported"] == result["unsupported"]


def test_create_styles_from_html_runtime_accepts_html_file() -> None:
    result = create_styles_from_html_runtime(
        profile="smoke",
        style_prefix="HTML",
        element_type="Button",
        html_file="tests/fixtures/html/style-states.html",
        selector=".btn-primary",
        execute=False,
    )

    assert result["ok"] is True
    assert result["style_count"] == 1
    assert result["operation_count"] == 6
    assert result["styles"][0]["states"]["pressed"]["bg_color"] == "#00359e"


def test_create_styles_from_html_runtime_executes_operations_with_executor() -> None:
    calls = []

    def fake_executor(tool: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((tool, arguments))
        return {"ok": True, "tool": tool}

    result = create_styles_from_html_runtime(
        profile="smoke",
        style_prefix="HTML",
        element_type="Button",
        html_file="tests/fixtures/html/style-states.html",
        selector=".btn-primary",
        execute=True,
        executor=fake_executor,
    )

    assert result["ok"] is True
    assert result["executed"] is True
    assert [tool for tool, _arguments in calls] == [
        "create_style",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "reorder_style_states",
    ]
    assert calls[0][1]["execute"] is True
    assert result["execution_results"][0]["tool"] == "create_style"


def test_create_styles_from_html_runtime_rejects_execute_without_executor() -> None:
    try:
        create_styles_from_html_runtime(
            profile="smoke",
            style_prefix="HTML",
            element_type="Button",
            html_file="tests/fixtures/html/style-states.html",
            selector=".btn-primary",
            execute=True,
        )
    except ValueError as exc:
        assert "requires an executor" in str(exc)
    else:
        raise AssertionError("Expected execute=true without executor to fail.")


def test_build_style_import_plan_can_infer_selector() -> None:
    result = build_style_import_plan(
        """
        <style>
          .btn-primary { color: #ffffff; }
          .btn-primary:hover { color: #eeeeee; }
        </style>
        <button class="btn-primary">Save</button>
        """,
        profile="smoke",
        style_name_prefix="HTML",
        element_type="Button",
        execute=False,
    )

    assert result["selector"] == ".btn-primary"
    assert result["candidates"][0]["states"]["hover"]["font_color"] == "#eeeeee"
