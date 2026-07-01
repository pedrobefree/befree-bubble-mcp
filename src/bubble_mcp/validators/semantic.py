"""Semantic validation for bootstrap Bubble plans."""

from __future__ import annotations

from typing import Any


READ_ONLY_TOOLS = {
    "bubble_health_check",
    "bubble_profile_list",
    "context_summary",
    "context_search",
}

MUTATING_TOOLS = {
    "create_text",
    "create_group",
    "bubble_editor_write",
}

REQUIRED_ARGS = {
    "create_text": {"context", "content"},
    "create_group": {"context", "name"},
    "bubble_editor_write": {"write_payload"},
}


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate a serialized plan."""

    errors: list[str] = []
    warnings: list[str] = []
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return {"ok": False, "errors": ["Plan must contain a steps array."], "warnings": []}

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step {index + 1} must be an object.")
            continue
        tool_name = str(step.get("tool_name") or "")
        raw_args = step.get("args")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        if tool_name not in READ_ONLY_TOOLS and tool_name not in MUTATING_TOOLS:
            errors.append(f"Unsupported tool: {tool_name or '<empty>'}.")
            continue
        missing = sorted(REQUIRED_ARGS.get(tool_name, set()) - set(args.keys()))
        if missing:
            errors.append(f"{tool_name} missing required args: {', '.join(missing)}.")
        if "write_payload" in args:
            payload = args.get("write_payload")
            if not isinstance(payload, dict):
                errors.append(f"{tool_name} write_payload must be an object.")
            elif not isinstance(payload.get("changes"), list):
                errors.append(f"{tool_name} write_payload must include a changes array.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
