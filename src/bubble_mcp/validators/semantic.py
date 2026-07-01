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
}

REQUIRED_ARGS = {
    "create_text": {"context", "content"},
    "create_group": {"context", "name"},
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
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        if tool_name not in READ_ONLY_TOOLS and tool_name not in MUTATING_TOOLS:
            errors.append(f"Unsupported tool: {tool_name or '<empty>'}.")
            continue
        missing = sorted(REQUIRED_ARGS.get(tool_name, set()) - set(args.keys()))
        if missing:
            errors.append(f"{tool_name} missing required args: {', '.join(missing)}.")
        if tool_name in MUTATING_TOOLS and args.get("dry_run") is not True:
            errors.append(f"{tool_name} must include dry_run=true in the bootstrap package.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
