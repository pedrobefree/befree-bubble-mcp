from bubble_mcp.language.compiler import compile_framework_program
from bubble_mcp.language.dependencies import (
    DependencyState,
    record_step_outputs,
    resolve_step_arguments,
)
from bubble_mcp.language.intents import INTENT_CATALOG, normalize_intent_arguments, tool_for_intent
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


def test_intent_catalog_covers_v2_families() -> None:
    families = {entry.family for entry in INTENT_CATALOG.values()}

    assert {
        "visual",
        "workflow",
        "data",
        "api_connector",
        "style",
        "reusable",
        "migration",
        "performance",
        "verification",
    }.issubset(families)


def test_compile_framework_program_maps_data_workflow_and_verification_intents(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Add enrollment data and event",
            "steps": [
                {"intent": "create_data_type", "name": "Enrollment"},
                {
                    "intent": "create_field",
                    "data_type": "Enrollment",
                    "name": "student",
                    "field_type": "User",
                },
                {"intent": "create_custom_event", "context": "checkout", "name": "Enroll student"},
                {"intent": "refresh_context"},
                {"intent": "verify_context", "query": "Enrollment", "exact": True},
            ],
        },
    )

    assert result["ok"] is True
    assert [call["tool"] for call in result["compiled_calls"]] == [
        "create_data_type",
        "create_data_field",
        "create_event",
        "bubble_profile_cache_refresh",
        "bubble_context_find",
    ]
    assert result["compiled_calls"][0]["arguments"]["profile"] == "cliente2"
    assert result["compiled_calls"][0]["arguments"]["execute"] is False
    assert result["compiled_calls"][4]["arguments"]["exact"] is True


def test_compile_framework_program_requires_data_field_type(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Add enrollment field",
            "steps": [
                {"intent": "create_field", "data_type": "Enrollment", "name": "student"},
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"] == "framework_program_missing_required_arguments"
    assert result["missing_arguments"] == [
        {
            "step": 1,
            "tool": "create_data_field",
            "missing": ["type"],
            "required": ["profile", "data_type_ref", "name", "type"],
        }
    ]


def test_resolve_step_arguments_uses_prior_step_outputs() -> None:
    state = DependencyState()
    record_step_outputs(
        state,
        step_id="section",
        declared_outputs={"element_id": "checkout_section"},
        result={"element_id": "group_123"},
    )

    args = resolve_step_arguments(
        {"parent": "{{steps.section.output.element_id}}", "context": "checkout"},
        state,
    )

    assert args == {"parent": "group_123", "context": "checkout"}


def test_resolve_step_arguments_reports_unresolved_placeholders() -> None:
    state = DependencyState()

    args = resolve_step_arguments({"parent": "{{steps.missing.output.element_id}}"}, state)

    assert args == {"parent": "{{steps.missing.output.element_id}}"}
    assert state.unresolved == ["{{steps.missing.output.element_id}}"]


def test_compile_framework_program_rejects_unresolved_mutating_dependency(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Create dependent CTA",
            "steps": [
                {
                    "id": "cta",
                    "intent": "create_button",
                    "context": "checkout",
                    "parent": "{{steps.section.output.element_id}}",
                    "text": "Start checkout",
                }
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"] == "framework_program_has_unresolved_dependencies"
    assert result["unresolved_dependencies"] == ["{{steps.section.output.element_id}}"]


def test_normalize_intent_arguments_maps_api_connector_aliases() -> None:
    args = normalize_intent_arguments(
        "create_api_call",
        {
            "label": "CRM create contact",
            "verb": "POST",
            "endpoint": "https://example.com/contacts",
        },
    )

    assert args["name"] == "CRM create contact"
    assert args["method"] == "POST"
    assert args["url"] == "https://example.com/contacts"


def test_tool_for_intent_maps_api_connector_aliases() -> None:
    assert tool_for_intent("create_api_connector_resource") == "create_api_connector_resource"
    assert tool_for_intent("api_call") == "create_api_connector_resource"
