from bubble_mcp.language.program import (
    FrameworkProgram,
    FrameworkProgramStep,
    parse_framework_program,
)


def test_parse_framework_program_normalizes_steps_and_execution_policy() -> None:
    result = parse_framework_program(
        {
            "objective": "Create checkout UI",
            "execution": {"mode": "preview", "approval": "required"},
            "steps": [
                {
                    "id": "section",
                    "intent": "create_container",
                    "context": "checkout",
                    "parent": "root",
                    "label": "Checkout section",
                    "outputs": {"element_id": "checkout_section"},
                },
                {
                    "id": "cta",
                    "intent": "cta_button",
                    "arguments": {
                        "context": "checkout",
                        "parent": "{{steps.section.output.element_id}}",
                        "text": "Start checkout",
                    },
                },
            ],
        }
    )

    assert isinstance(result, FrameworkProgram)
    assert result.objective == "Create checkout UI"
    assert result.execution_mode == "preview"
    assert result.approval == "required"
    assert [step.step_id for step in result.steps] == ["section", "cta"]
    assert result.steps[0].arguments["label"] == "Checkout section"
    assert result.steps[1].arguments["parent"] == "{{steps.section.output.element_id}}"


def test_parse_framework_program_rejects_missing_steps() -> None:
    result = parse_framework_program({"objective": "Empty"})

    assert result.ok is False
    assert result.error == "framework_program_has_no_steps"


def test_framework_program_step_keeps_direct_tool_calls() -> None:
    step = FrameworkProgramStep.from_dict(
        {
            "id": "refresh",
            "tool": "bubble_profile_cache_refresh",
            "arguments": {"force": True},
        },
        index=1,
    )

    assert step.step_id == "refresh"
    assert step.tool == "bubble_profile_cache_refresh"
    assert step.intent == ""
    assert step.arguments == {"force": True}
