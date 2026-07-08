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
        style_name="Primary Button",
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
    assert result["style_name"] == "Primary Button"
    assert result["identity"] == {
        "style_name": "Primary Button",
        "element_type": "Button",
        "match": "name_and_element_type",
        "mode": "upsert",
    }
    assert result["candidates"][0]["name"] == "Primary Button"
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
        style_name="Primary Button",
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
        style_name="Primary Button",
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


def test_create_styles_from_html_runtime_uses_rendered_html_for_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_render_url_to_html(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["url"] == "https://example.test/button"
        assert kwargs["selector"] == ".btn-primary"
        assert kwargs["timeout_ms"] == 35000
        return """
        <style>
          .btn-primary:hover { background-color: rgb(0, 78, 235); }
        </style>
        <button class="btn-primary" style="background-color: rgb(21, 94, 239); color: rgb(255, 255, 255);">
          Save
        </button>
        """

    monkeypatch.setattr("bubble_mcp.style_import.runtime.render_url_to_html", fake_render_url_to_html)

    result = create_styles_from_html_runtime(
        profile="smoke",
        style_name="Primary Button",
        element_type="Button",
        url="https://example.test/button",
        selector=".btn-primary",
        execute=False,
        rendered_html=True,
    )

    assert result["ok"] is True
    assert result["source"] == {
        "type": "url",
        "url": "https://example.test/button",
        "rendered_html": True,
        "selector": ".btn-primary",
    }
    assert result["styles"][0]["base"]["bg_color"] == "#155eef"
    assert result["styles"][0]["states"]["hover"]["bg_color"] == "#004eeb"


def test_create_styles_from_html_runtime_requires_selector_for_url() -> None:
    try:
        create_styles_from_html_runtime(
            profile="smoke",
            style_name="Primary Button",
            element_type="Button",
            url="https://example.test/button",
            execute=False,
        )
    except ValueError as exc:
        assert "requires selector" in str(exc)
    else:
        raise AssertionError("Expected URL style import without selector to fail.")


def test_create_styles_from_html_runtime_executes_operations_with_executor() -> None:
    calls = []

    def fake_executor(tool: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((tool, arguments))
        return {"ok": True, "tool": tool}

    def fake_verifier(candidate: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "style_name": candidate["name"], "element_type": candidate["element_type"]}

    result = create_styles_from_html_runtime(
        profile="smoke",
        style_name="Primary Button",
        style_prefix="HTML",
        element_type="Button",
        html_file="tests/fixtures/html/style-states.html",
        selector=".btn-primary",
        execute=True,
        executor=fake_executor,
        verifier=fake_verifier,
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
    assert result["verified"] is True
    assert result["verification"]["style_name"] == "Primary Button"


def test_create_styles_from_html_runtime_rejects_execute_without_executor() -> None:
    try:
        create_styles_from_html_runtime(
            profile="smoke",
            style_name="Primary Button",
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


def test_create_styles_from_html_runtime_rejects_execute_without_verifier() -> None:
    try:
        create_styles_from_html_runtime(
            profile="smoke",
            style_name="Primary Button",
            style_prefix="HTML",
            element_type="Button",
            html_file="tests/fixtures/html/style-states.html",
            selector=".btn-primary",
            execute=True,
            executor=lambda _tool, _arguments: {"ok": True},
        )
    except ValueError as exc:
        assert "requires a verifier" in str(exc)
    else:
        raise AssertionError("Expected execute=true without verifier to fail.")


def test_build_style_import_plan_requires_style_identity() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")

    try:
        build_style_import_plan(html, profile="smoke", selector=".btn-primary", element_type="Button")
    except ValueError as exc:
        assert "requires style_name" in str(exc)
    else:
        raise AssertionError("Expected missing style_name to fail.")


def test_build_style_import_plan_requires_element_type() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")

    try:
        build_style_import_plan(html, profile="smoke", selector=".btn-primary", style_name="Primary Button")
    except ValueError as exc:
        assert "requires element_type" in str(exc)
    else:
        raise AssertionError("Expected missing element_type to fail.")


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
        style_name="Primary Button",
        style_name_prefix="HTML",
        element_type="Button",
        execute=False,
    )

    assert result["selector"] == ".btn-primary"
    assert result["candidates"][0]["states"]["hover"]["font_color"] == "#eeeeee"
