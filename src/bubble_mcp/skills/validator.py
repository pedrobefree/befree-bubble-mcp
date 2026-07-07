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
EXECUTABLE_INPUT_TYPES = {"array", "boolean", "integer", "number", "object", "string"}
EXECUTABLE_RISKS = {"read_only", "mutating", "destructive"}
EXECUTABLE_STEP_MODES = {"read", "preview", "write"}
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
        "executable": bool(skill.executable) if skill else False,
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


def _is_executable_contract(payload: Mapping[str, Any]) -> bool:
    if "risk" in payload or "approval" in payload:
        return True
    raw_inputs = payload.get("inputs")
    if isinstance(raw_inputs, Mapping):
        return True
    raw_steps = payload.get("steps")
    if isinstance(raw_steps, list):
        return any(isinstance(step, Mapping) and step.get("type") == "tool" for step in raw_steps)
    return False


def _validate_input_schema(payload: Mapping[str, Any], errors: list[str]) -> None:
    raw_inputs = payload.get("inputs")
    if raw_inputs is None:
        return
    if not isinstance(raw_inputs, Mapping):
        errors.append("inputs must be an object for executable skill contracts")
        return
    for input_name, input_schema in raw_inputs.items():
        if not isinstance(input_name, str) or not input_name.strip():
            errors.append("inputs keys must be non-empty strings")
            continue
        if not isinstance(input_schema, Mapping):
            errors.append(f"inputs.{input_name} must be an object")
            continue
        input_type = input_schema.get("type")
        if input_type not in EXECUTABLE_INPUT_TYPES:
            errors.append(f"inputs.{input_name}.type must be one of: {', '.join(sorted(EXECUTABLE_INPUT_TYPES))}")
        if "required" in input_schema and not isinstance(input_schema.get("required"), bool):
            errors.append(f"inputs.{input_name}.required must be boolean")


def _validate_approval(payload: Mapping[str, Any], risk: str, errors: list[str]) -> None:
    raw_approval = payload.get("approval")
    if risk not in {"mutating", "destructive"}:
        if raw_approval is not None and not isinstance(raw_approval, Mapping):
            errors.append("approval must be an object")
        return
    if not isinstance(raw_approval, Mapping):
        errors.append("mutating and destructive skills require approval object")
        return
    if raw_approval.get("mode") != "plan_then_approve":
        errors.append("mutating and destructive skills require approval.mode=plan_then_approve")
    raw_required_for = raw_approval.get("requiredFor", [])
    if not isinstance(raw_required_for, list) or risk not in [str(item) for item in raw_required_for]:
        errors.append(f"approval.requiredFor must include {risk}")


def _validate_executable_steps(
    payload: Mapping[str, Any],
    *,
    risk: str,
    allowed_tools: list[str],
    available_tools: set[str],
    errors: list[str],
) -> None:
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        errors.append("steps must be a non-empty list")
        return
    allowed_tool_set = set(allowed_tools)
    seen_step_ids: set[str] = set()
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, Mapping):
            errors.append(f"steps[{index}] must be an object")
            continue
        step_id = raw_step.get("id")
        if not isinstance(step_id, str) or not step_id.strip():
            errors.append(f"steps[{index}].id is required")
        elif step_id in seen_step_ids:
            errors.append(f"steps[{index}].id duplicates step id: {step_id}")
        else:
            seen_step_ids.add(step_id)
        step_type = raw_step.get("type")
        if step_type != "tool":
            errors.append(f"steps[{index}].type must be tool for executable skill contracts")
            continue
        if _is_executable_step_type(str(step_type)):
            errors.append(f"steps[{index}].type is forbidden: {step_type}")
        tool_name = raw_step.get("tool")
        if not isinstance(tool_name, str) or not tool_name.strip():
            errors.append(f"steps[{index}].tool is required")
        else:
            if tool_name not in allowed_tool_set:
                errors.append(f"steps[{index}].tool is not listed in allowedTools: {tool_name}")
            if tool_name not in available_tools:
                errors.append(f"steps[{index}].tool references unknown tool: {tool_name}")
        mode = raw_step.get("mode")
        if mode not in EXECUTABLE_STEP_MODES:
            errors.append(f"steps[{index}].mode must be one of: {', '.join(sorted(EXECUTABLE_STEP_MODES))}")
        if mode == "write" and risk not in {"mutating", "destructive"}:
            errors.append(f"steps[{index}].mode=write requires risk mutating or destructive")
        if "args" in raw_step and not isinstance(raw_step.get("args"), Mapping):
            errors.append(f"steps[{index}].args must be an object")
        raw_depends_on = raw_step.get("dependsOn")
        if raw_depends_on is not None:
            _validate_string_sequence(raw_depends_on, f"steps[{index}].dependsOn", errors, required=False)


def _validate_executable_gates(payload: Mapping[str, Any], risk: str, errors: list[str]) -> None:
    raw_gates = payload.get("gates")
    if raw_gates is None:
        raw_gates = []
    if not isinstance(raw_gates, list):
        errors.append("gates must be a list of objects")
        return
    has_approval_gate = False
    for index, raw_gate in enumerate(raw_gates):
        if not isinstance(raw_gate, Mapping):
            errors.append(f"gates[{index}] must be an object")
            continue
        gate_type = raw_gate.get("type")
        if not isinstance(gate_type, str) or not gate_type.strip():
            errors.append(f"gates[{index}].type is required")
            continue
        if gate_type == "approval_required":
            has_approval_gate = True
            raw_when_risk = raw_gate.get("whenRisk", [])
            if not isinstance(raw_when_risk, list) or risk not in [str(item) for item in raw_when_risk]:
                errors.append(f"gates[{index}].whenRisk must include {risk}")
        if gate_type == "evidence_required":
            _validate_string_sequence(raw_gate.get("outputs"), f"gates[{index}].outputs", errors, required=True)
    if risk in {"mutating", "destructive"} and not has_approval_gate:
        errors.append("mutating and destructive skills require approval_required gate")


def _validate_legacy_steps(payload: Mapping[str, Any], errors: list[str]) -> None:
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

    executable = _is_executable_contract(payload)
    if executable:
        _validate_input_schema(payload, errors)
    else:
        _validate_string_list(payload, "inputs", errors, required=False)
    allowed_tools = _validate_string_list(payload, "allowedTools", errors, required=True)
    tool_names = available_tools if available_tools is not None else _available_tool_names()
    if allowed_tools:
        for tool_name in allowed_tools:
            if tool_name not in tool_names:
                errors.append(f"allowedTools references unknown tool: {tool_name}")

    risk = str(payload.get("risk") or "read_only").strip()
    if executable:
        if risk not in EXECUTABLE_RISKS:
            errors.append(f"risk must be one of: {', '.join(sorted(EXECUTABLE_RISKS))}")
        _validate_approval(payload, risk, errors)
        _validate_executable_steps(
            payload,
            risk=risk,
            allowed_tools=allowed_tools,
            available_tools=tool_names,
            errors=errors,
        )
        _validate_executable_gates(payload, risk, errors)
    else:
        _validate_legacy_steps(payload, errors)
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
    if executable:
        raw_gates = payload.get("gates")
        if not isinstance(raw_gates, list):
            pass

    _validate_string_list(payload, "outputs", errors, required=True)

    if errors:
        return _error_report(errors)
    normalized_payload = dict(payload)
    normalized_payload["executable"] = executable
    skill = SkillDefinition.from_dict(normalized_payload)
    return {"ok": True, "skill": skill.to_dict(), "executable": executable, "errors": []}


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
