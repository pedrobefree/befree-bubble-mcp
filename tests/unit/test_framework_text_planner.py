from bubble_mcp.frameworks.text_planner import plan_framework_text


def test_plan_framework_text_extracts_visual_and_verification_steps() -> None:
    result = plan_framework_text(
        framework="superpowers",
        profile="cliente2",
        text="""
        Objective: Build checkout CTA.
        - Find page checkout.
        - Create a section named Checkout controls inside root.
        - Add button labeled Start checkout inside Checkout controls.
        - Refresh cache and verify Start checkout exists.
        """,
    )

    assert result["ok"] is True
    assert result["program"]["objective"] == "Build checkout CTA."
    assert [step["intent"] for step in result["program"]["steps"]] == [
        "verify_context",
        "create_container",
        "create_button",
        "refresh_context",
        "verify_context",
    ]


def test_plan_framework_text_returns_questions_for_ambiguous_mutation() -> None:
    result = plan_framework_text(
        framework="bmad",
        profile="cliente2",
        text="Create the thing on the page.",
    )

    assert result["ok"] is False
    assert result["error"] == "framework_text_requires_clarification"
    assert result["questions"]


def test_plan_framework_text_sets_button_defaults_without_parent_hint() -> None:
    result = plan_framework_text(
        framework="bmad",
        profile="cliente2",
        text="""
        Objective: Add login action.
        - Create button labeled Pay now.
        """,
    )

    assert result["ok"] is True
    button = result["program"]["steps"][0]
    assert button["intent"] == "create_button"
    assert button["text"] == "Pay now"
    assert button["parent"] == "root"


def test_plan_framework_text_uses_story_as_objective() -> None:
    result = plan_framework_text(
        framework="bmad",
        profile="cliente2",
        text="""
        Story: Add checkout payment button.
        - Create button labeled Pay now.
        """,
    )

    assert result["ok"] is True
    assert result["program"]["objective"] == "Add checkout payment button."


def test_plan_framework_text_uses_first_useful_line_as_objective() -> None:
    result = plan_framework_text(
        framework="superpowers",
        profile="cliente2",
        text="""
        Add primary checkout action.
        - Create button labeled Pay now.
        """,
    )

    assert result["ok"] is True
    assert result["program"]["objective"] == "Add primary checkout action."
