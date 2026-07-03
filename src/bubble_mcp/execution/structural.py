"""Structural plan validation for agent-safe execution."""

from __future__ import annotations

from typing import Any

from bubble_mcp.execution.executor_types import extract_write_payload
from bubble_mcp.validators.semantic import validate_write_payload


DESTRUCTIVE_PREFIXES = ("delete_", "remove_", "clear_")
DESTRUCTIVE_TOOLS = {
    "bubble_branch_delete",
    "delete_element",
    "delete_text",
    "delete_button",
    "delete_group",
    "delete_page",
    "delete_workflow",
    "delete_data_type",
    "delete_data_field",
    "delete_option_set",
    "delete_option_value",
}


def is_destructive_tool(tool_name: str) -> bool:
    normalized = str(tool_name or "").strip()
    return normalized in DESTRUCTIVE_TOOLS or normalized.startswith(DESTRUCTIVE_PREFIXES)


def _step_id(step: dict[str, Any], index: int) -> str:
    return str(step.get("id") or f"step_{index + 1}")


def _depends_on(step: dict[str, Any]) -> list[str]:
    raw = step.get("depends_on")
    if raw is None:
        raw = step.get("dependsOn")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def validate_structure(plan: dict[str, Any], *, execute: bool = False) -> dict[str, Any]:
    """Validate step graph, executable payloads, and confirmation requirements."""

    errors: list[str] = []
    warnings: list[str] = []
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return {
            "ok": False,
            "status": "blocked",
            "errors": ["Plan must contain a steps array."],
            "warnings": [],
            "correction_guidance": ["Return a plan object with steps[]."],
        }

    seen: set[str] = set()
    all_ids: set[str] = set()
    normalized_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            errors.append(f"Step {index + 1} must be an object.")
            continue
        step_id = _step_id(raw_step, index)
        if step_id in all_ids:
            errors.append(f"Duplicate step id: {step_id}.")
        all_ids.add(step_id)
        normalized_steps.append(raw_step)

    for index, step in enumerate(normalized_steps):
        step_id = _step_id(step, index)
        tool_name = str(step.get("tool_name") or "")
        dependencies = _depends_on(step)
        for dependency in dependencies:
            if dependency == step_id:
                errors.append(f"{step_id} cannot depend on itself.")
            elif dependency not in all_ids:
                errors.append(f"{step_id} depends on unknown step id: {dependency}.")
            elif dependency not in seen:
                warnings.append(f"{step_id} depends on a later step: {dependency}.")
        seen.add(step_id)

        payload = extract_write_payload(step)
        if payload is not None:
            payload_errors = validate_write_payload(payload)
            errors.extend(f"{step_id} {error}" for error in payload_errors)
        elif execute:
            errors.append(f"{step_id} has no write_payload. Compile the plan before execute=true.")

        raw_args = step.get("args")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        if execute and is_destructive_tool(tool_name) and not bool(args.get("confirm") or args.get("approved")):
            errors.append(f"{step_id} uses destructive tool {tool_name} without confirm=true.")

    status = "blocked" if errors else ("executable" if execute else "previewable")
    guidance: list[str] = []
    if any("no write_payload" in error for error in errors):
        guidance.append("Call bubble_compile_plan or bubble_execute_plan with compile=true before executing.")
    if any("destructive" in error for error in errors):
        guidance.append("Ask the user for explicit approval and pass confirm=true for destructive steps.")
    if any("depends on" in error for error in errors):
        guidance.append("Fix depends_on so every dependency references an existing prior step id.")
    if any("write_payload" in error and "missing" in error for error in errors):
        guidance.append("Regenerate the Bubble write payload from the current project context.")

    return {
        "ok": not errors,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "correction_guidance": guidance,
    }
