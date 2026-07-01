from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.validators.semantic import validate_plan


def test_plans_create_text() -> None:
    plan = plan_message('Create a text saying "Hello"', context="index")

    payload = plan.to_dict()

    assert payload["steps"][0]["tool_name"] == "create_text"
    assert payload["steps"][0]["args"]["content"] == "Hello"
    assert validate_plan(payload)["ok"] is True


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
