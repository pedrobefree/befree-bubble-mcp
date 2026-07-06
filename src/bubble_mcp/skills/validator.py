"""Validation for declarative Bubble MCP skill contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bubble_mcp.extensions.tools import enabled_extension_tool_schemas
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.server.schema_families import native_tool_schemas
from bubble_mcp.skills.models import SkillDefinition


ALLOWED_SKILL_STEP_TYPES = {
    "generate_report",
    "inspect_privacy_rules",
    "inspect_schema",
    "inspect_workflows",
    "refresh_context",
}
EXECUTABLE_STEP_TOKENS = {
    "bash",
    "cmd",
    "command",
    "exec",
    "execute",
    "eval",
    "fish",
    "javascript",
    "js",
    "node",
    "python",
    "sh",
    "shell",
    "subprocess",
    "system",
    "zsh",
}
STEP_TYPE_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")


def _executable_step_tokens(step_type: str) -> set[str]:
    normalized = step_type.strip().lower()
    return {token for token in STEP_TYPE_TOKEN_PATTERN.split(normalized) if token}


def _is_executable_step_type(step_type: str) -> bool:
    return bool(_executable_step_tokens(step_type) & EXECUTABLE_STEP_TOKENS)


def _available_tool_names() -> set[str]:
    names = {str(tool.get("name") or "") for tool in native_tool_schemas()}
    names.update(ARIA_BUBBLE_TOOL_NAMES)
    for tool in enabled_extension_tool_schemas():
        names.add(str(tool.get("name") or ""))
    return {name for name in names if name}


def _error_report(errors: list[str], skill: SkillDefinition | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "skill": skill.to_dict() if skill else None,
        "errors": errors,
    }


def _validate_string_sequence(
    raw_value: Any,
    label: str,
    errors: list[str],
    *,
    required: bool,
) -> list[str]:
    if raw_value is None:
        if required:
            errors.append(f"{label} must be a non-empty list of strings")
        return []
    if not isinstance(raw_value, list):
        errors.append(f"{label} must be a list of strings")
        return []

    values: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue
        values.append(item.strip())
    if required and not values:
        errors.append(f"{label} must be a non-empty list of strings")
    return values


def _validate_string_list(
    payload: Mapping[str, Any],
    key: str,
    errors: list[str],
    *,
    required: bool,
) -> list[str]:
    return _validate_string_sequence(payload.get(key), key, errors, required=required)


def validate_skill_payload(payload: Any, *, available_tools: set[str] | None = None) -> dict[str, Any]:
    """Validate one declarative skill payload."""

    if not isinstance(payload, Mapping):
        return _error_report(["skill file must contain a JSON object"])

    errors: list[str] = []

    raw_id = payload.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        errors.append("id is required")

    raw_name = payload.get("name")
    if raw_name is not None and not isinstance(raw_name, str):
        errors.append("name must be a string")

    _validate_string_list(payload, "inputs", errors, required=False)
    allowed_tools = _validate_string_list(payload, "allowedTools", errors, required=True)
    if allowed_tools:
        tool_names = available_tools if available_tools is not None else _available_tool_names()
        for tool_name in allowed_tools:
            if tool_name not in tool_names:
                errors.append(f"allowedTools references unknown tool: {tool_name}")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        errors.append("steps must be a non-empty list")
    else:
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, Mapping):
                errors.append(f"steps[{index}] must be an object")
                continue
            step_type = raw_step.get("type")
            if not isinstance(step_type, str) or not step_type.strip():
                errors.append(f"steps[{index}].type is required")
                continue
            normalized_step_type = step_type.strip().lower()
            if normalized_step_type not in ALLOWED_SKILL_STEP_TYPES:
                errors.append(f"steps[{index}].type is not allowed in skill contract v1: {step_type.strip()}")
                continue
            if _is_executable_step_type(step_type):
                errors.append(f"steps[{index}].type is forbidden: {step_type.strip()}")

    raw_gates = payload.get("gates")
    if raw_gates is not None:
        if not isinstance(raw_gates, list):
            errors.append("gates must be a list of objects")
        else:
            for index, raw_gate in enumerate(raw_gates):
                if not isinstance(raw_gate, Mapping):
                    errors.append(f"gates[{index}] must be an object")
                    continue
                gate_type = raw_gate.get("type")
                if not isinstance(gate_type, str) or not gate_type.strip():
                    errors.append(f"gates[{index}].type is required")
                    continue
                if gate_type.strip().lower() == "evidence_required":
                    _validate_string_sequence(
                        raw_gate.get("outputs"),
                        f"gates[{index}].outputs",
                        errors,
                        required=True,
                    )

    _validate_string_list(payload, "outputs", errors, required=True)

    if errors:
        return _error_report(errors)
    skill = SkillDefinition.from_dict(payload)
    return {"ok": True, "skill": skill.to_dict(), "errors": []}


def validate_skill_file(path: Path) -> dict[str, Any]:
    """Validate one declarative skill JSON file and return a report."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _error_report([f"invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"])
    except OSError as exc:
        return _error_report([str(exc)])
    return validate_skill_payload(payload)


def describe_skill_file(path: Path) -> dict[str, Any]:
    """Return a validation-backed description of a skill contract."""

    report = validate_skill_file(path)
    return {
        **report,
        "description": "Declarative skill contract validation only; execution is not implemented.",
    }
