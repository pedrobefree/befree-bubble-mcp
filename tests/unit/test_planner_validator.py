from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.validators.semantic import validate_plan


def test_plans_create_text_dry_run() -> None:
    plan = plan_message('Create a text saying "Hello"', context="index")

    payload = plan.to_dict()

    assert payload["steps"][0]["tool_name"] == "create_text"
    assert payload["steps"][0]["args"]["content"] == "Hello"
    assert validate_plan(payload)["ok"] is True


def test_destructive_request_requires_approval_and_has_no_steps() -> None:
    plan = plan_message("delete the user table")

    assert plan.requires_approval is True
    assert plan.steps == []


def test_validation_rejects_mutation_without_dry_run() -> None:
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

    assert result["ok"] is False
    assert "dry_run=true" in result["errors"][0]
