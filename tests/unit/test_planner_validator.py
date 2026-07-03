from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.validators.semantic import validate_plan, validate_write_payload


def test_plans_create_text() -> None:
    plan = plan_message('Create a text saying "Hello"', context="index")

    payload = plan.to_dict()

    assert payload["steps"][0]["tool_name"] == "create_text"
    assert payload["steps"][0]["args"]["content"] == "Hello"
    assert validate_plan(payload)["ok"] is True
    assert payload["routing"]["parser"] == "example_match"


def test_plan_routes_button_from_example_corpus() -> None:
    plan = plan_message('Create a button labeled "Get started" on page landing', context="index")

    payload = plan.to_dict()

    assert payload["steps"][0]["tool_name"] == "create_button"
    assert payload["steps"][0]["args"]["context"] == "landing"
    assert payload["steps"][0]["args"]["label"] == "Get started"
    assert payload["routing"]["parser"] == "example_match"


def test_plan_routes_rendered_html_import_from_url_and_selector() -> None:
    plan = plan_message(
        "Converta o componente com seletor #home-area da URL https://example.com/page.html "
        "e adicione na pagina mcp-01",
        context="index",
    )

    payload = plan.to_dict()

    assert payload["steps"][0]["tool_name"] == "create_from_html"
    assert payload["steps"][0]["args"]["context"] == "mcp-01"
    assert payload["steps"][0]["args"]["url"] == "https://example.com/page.html"
    assert payload["steps"][0]["args"]["selector"] == "#home-area"
    assert payload["steps"][0]["args"]["rendered_html"] is True
    assert payload["steps"][0]["args"]["refresh_context"] is True


def test_destructive_request_requires_approval_and_has_no_steps() -> None:
    plan = plan_message("delete the user table")

    assert plan.requires_approval is True
    assert plan.steps == []


def test_validation_accepts_mutation_without_forced_dry_run() -> None:
    result = validate_plan(
        {
            "steps": [
                {
                    "tool_name": "create_text",
                    "args": {"context": "index", "content": "Hello"},
                }
            ]
        }
    )

    assert result["ok"] is True


def test_validation_checks_write_payload_shape() -> None:
    result = validate_plan(
        {
            "steps": [
                {
                    "tool_name": "bubble_editor_write",
                    "args": {"write_payload": {"appname": "synthetic-app"}},
                }
            ]
        }
    )

    assert result["ok"] is False
    assert "changes array" in result["errors"][0]


def test_validate_write_payload_accepts_create_element() -> None:
    errors = validate_write_payload(
        {
            "appname": "synthetic-app",
            "changes": [
                {
                    "intent": {"name": "CreateElement"},
                    "path_array": ["%p3", "index"],
                    "body": {"%x": "Text", "%p": {"%nm": "Title", "%3": "Hello"}},
                }
            ],
        }
    )

    assert errors == []


def test_validate_write_payload_rejects_create_element_property_path() -> None:
    errors = validate_write_payload(
        {
            "appname": "synthetic-app",
            "changes": [
                {
                    "intent": {"name": "CreateElement"},
                    "path_array": ["%p3", "index", "%p", "%3"],
                    "body": {"%x": "Text", "%p": {"%nm": "Title"}},
                }
            ],
        }
    )

    assert any("must not include %p" in error for error in errors)
