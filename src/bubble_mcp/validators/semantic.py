"""Semantic validation for bootstrap Bubble plans."""

from __future__ import annotations

from typing import Any

from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES


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
CATALOG_TOOLS = set(ARIA_BUBBLE_TOOL_NAMES)

REQUIRED_ARGS = {
    "create_text": {"context", "content"},
    "create_group": {"context", "name"},
    "bubble_editor_write": {"write_payload"},
}


def validate_write_payload(payload: dict[str, Any]) -> list[str]:
    """Return semantic errors for a Bubble /appeditor/write payload."""

    errors: list[str] = []
    appname = str(payload.get("appname") or "").strip()
    if not appname:
        errors.append("write_payload missing appname.")
    changes = payload.get("changes")
    if not isinstance(changes, list):
        errors.append("write_payload must include a changes array.")
        return errors
    if not changes:
        errors.append("write_payload changes array must not be empty.")
        return errors

    for index, change in enumerate(changes):
        prefix = f"write_payload changes[{index}]"
        if not isinstance(change, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        intent = change.get("intent")
        if not isinstance(intent, dict) or not str(intent.get("name") or "").strip():
            errors.append(f"{prefix} missing intent.name.")
        path_array = change.get("path_array")
        if not isinstance(path_array, list) or not path_array:
            errors.append(f"{prefix} missing path_array.")
        elif "%p" in path_array and str(_intent_name(change)) == "CreateElement":
            errors.append(f"{prefix} CreateElement path_array must not include %p.")
        body = change.get("body")
        if _intent_name(change) == "CreateElement":
            if not isinstance(body, dict):
                errors.append(f"{prefix} CreateElement body must be an object.")
            else:
                element_type = str(body.get("%x") or body.get("type") or "").strip()
                properties = body.get("%p")
                if not element_type:
                    errors.append(f"{prefix} CreateElement body missing %x element type.")
                if not isinstance(properties, dict):
                    errors.append(f"{prefix} CreateElement body missing %p properties.")
                elif not str(properties.get("%nm") or properties.get("name") or "").strip():
                    errors.append(f"{prefix} CreateElement properties missing %nm name.")
    return errors


def _intent_name(change: dict[str, Any]) -> str:
    intent = change.get("intent")
    return str(intent.get("name") or "") if isinstance(intent, dict) else ""


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
        if tool_name not in READ_ONLY_TOOLS and tool_name not in MUTATING_TOOLS and tool_name not in CATALOG_TOOLS:
            errors.append(f"Unsupported tool: {tool_name or '<empty>'}.")
            continue
        missing = sorted(REQUIRED_ARGS.get(tool_name, set()) - set(args.keys()))
        if missing:
            errors.append(f"{tool_name} missing required args: {', '.join(missing)}.")
        if "write_payload" in args:
            payload = args.get("write_payload")
            if not isinstance(payload, dict):
                errors.append(f"{tool_name} write_payload must be an object.")
            else:
                errors.extend(f"{tool_name} {error}" for error in validate_write_payload(payload))

    return {"ok": not errors, "errors": errors, "warnings": warnings}
