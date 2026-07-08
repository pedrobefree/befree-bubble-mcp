"""Compile compact framework programs into preview-safe MCP calls."""

from __future__ import annotations

from typing import Any

from bubble_mcp.frameworks.adapters import get_adapter
from bubble_mcp.language.dependencies import (
    PLACEHOLDER_RE,
    DependencyState,
    resolve_step_arguments,
)
from bubble_mcp.language.intents import normalize_intent_arguments, tool_for_intent
from bubble_mcp.language.program import FrameworkProgramStep, parse_framework_program
from bubble_mcp.language.query import language_tool_detail
from bubble_mcp.server.schemas import list_tool_schemas


READ_ONLY_TOOLS = {
    "bubble_context_find",
    "bubble_context_summary",
    "bubble_profile_status",
    "bubble_tool_search",
    "bubble_task_runbook",
    "bubble_language_index",
    "bubble_language_query",
    "bubble_language_tool_detail",
    "bubble_language_diff",
}


def _available_tool_schemas() -> dict[str, dict[str, Any]]:
    return {str(tool.get("name") or ""): tool for tool in list_tool_schemas()}


def _schema_properties(tool_schema: dict[str, Any] | None) -> set[str]:
    raw_schema = tool_schema.get("inputSchema") if isinstance(tool_schema, dict) else {}
    input_schema: dict[str, Any] = raw_schema if isinstance(raw_schema, dict) else {}
    raw_properties = input_schema.get("properties")
    return {str(key) for key in raw_properties} if isinstance(raw_properties, dict) else set()


def _schema_required(tool_schema: dict[str, Any] | None) -> list[str]:
    raw_schema = tool_schema.get("inputSchema") if isinstance(tool_schema, dict) else {}
    input_schema: dict[str, Any] = raw_schema if isinstance(raw_schema, dict) else {}
    raw_required = input_schema.get("required")
    return [str(field) for field in raw_required] if isinstance(raw_required, list) else []


def _with_profile_and_preview(
    tool_name: str,
    args: dict[str, Any],
    profile: str,
    tool_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    compiled = dict(args)
    properties = _schema_properties(tool_schema)
    if profile and "profile" in properties and "profile" not in compiled:
        compiled["profile"] = profile
    if tool_name not in READ_ONLY_TOOLS and "execute" in properties:
        compiled["execute"] = False
    return compiled


def _compiled_call(
    *,
    step: FrameworkProgramStep,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    call: dict[str, Any] = {
        "step_id": step.step_id,
        "tool": tool_name,
        "arguments": arguments,
    }
    if step.intent:
        call["intent"] = step.intent
    return call


def _compile_intent_step(
    step: FrameworkProgramStep,
    step_arguments: dict[str, Any],
    profile: str,
    framework_id: str,
    tool_schemas: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    intent = step.intent
    tool_name = tool_for_intent(intent)
    if tool_name:
        raw_args = dict(step_arguments)
        if step.description:
            raw_args.setdefault("description", step.description)
        if tool_name == "bubble_framework_sync_evidence":
            raw_args.setdefault("framework", framework_id)
        args = normalize_intent_arguments(intent, raw_args)
        return _compiled_call(
            step=step,
            tool_name=tool_name,
            arguments=_with_profile_and_preview(tool_name, args, profile, tool_schemas.get(tool_name)),
        )
    return {
        "step_id": step.step_id,
        "tool": "bubble_tool_search",
        "arguments": {"query": intent or step.description, "limit": 8},
        "intent": intent,
        "unresolved_intent": intent,
    }


def _missing_required_arguments(
    compiled_calls: list[dict[str, Any]],
    tool_schemas: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    missing_items: list[dict[str, Any]] = []
    for index, call in enumerate(compiled_calls, start=1):
        tool_name = str(call.get("tool") or "")
        raw_args = call.get("arguments")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        required = _schema_required(tool_schemas.get(tool_name))
        missing = [field for field in required if args.get(field) in (None, "")]
        if missing:
            missing_items.append(
                {
                    "step": index,
                    "tool": tool_name,
                    "missing": missing,
                    "required": required,
                }
            )
    return missing_items


def _unresolved_placeholders_in(value: Any, known_unresolved: list[str]) -> list[str]:
    known = set(known_unresolved)
    found: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            for match in PLACEHOLDER_RE.finditer(item):
                placeholder = match.group(0)
                if placeholder in known and placeholder not in found:
                    found.append(placeholder)
        elif isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return found


def compile_framework_program(
    *,
    framework: str,
    profile: str,
    program: dict[str, Any],
) -> dict[str, Any]:
    adapter = get_adapter(framework)
    parsed = parse_framework_program(program)
    if not parsed.ok:
        return {
            "ok": False,
            "error": parsed.error,
            "framework": adapter.framework_id,
            "profile": profile,
        }
    tool_schemas = _available_tool_schemas()
    available = set(tool_schemas)
    compiled_calls: list[dict[str, Any]] = []
    unavailable: list[str] = []
    unresolved: list[str] = []
    unresolved_dependency_mutations: list[dict[str, Any]] = []
    dependency_state = DependencyState()
    for step in parsed.steps:
        step_arguments = resolve_step_arguments(step.arguments, dependency_state)
        step_unresolved_dependencies = _unresolved_placeholders_in(
            step_arguments,
            dependency_state.unresolved,
        )
        if step.tool:
            tool_name = step.tool
            if tool_name not in available:
                unavailable.append(tool_name)
                continue
            normalized_args = normalize_intent_arguments(tool_name, step_arguments)
            compiled_calls.append(
                _compiled_call(
                    step=step,
                    tool_name=tool_name,
                    arguments=_with_profile_and_preview(
                        tool_name,
                        normalized_args,
                        profile,
                        tool_schemas.get(tool_name),
                    ),
                )
            )
            if tool_name not in READ_ONLY_TOOLS and step_unresolved_dependencies:
                unresolved_dependency_mutations.append(compiled_calls[-1])
        else:
            compiled = _compile_intent_step(
                step,
                step_arguments,
                profile,
                adapter.framework_id,
                tool_schemas,
            )
            if compiled["tool"] not in available:
                unavailable.append(str(compiled["tool"]))
                continue
            if compiled.get("unresolved_intent"):
                unresolved.append(str(compiled["unresolved_intent"]))
                compiled.pop("unresolved_intent", None)
            compiled_calls.append(compiled)
            if str(compiled.get("tool") or "") not in READ_ONLY_TOOLS and step_unresolved_dependencies:
                unresolved_dependency_mutations.append(compiled)
    if unavailable:
        return {
            "ok": False,
            "error": "framework_program_has_unavailable_tools",
            "framework": adapter.framework_id,
            "profile": profile,
            "unavailable_tools": sorted(unavailable),
        }
    if dependency_state.unresolved and unresolved_dependency_mutations:
        return {
            "ok": False,
            "error": "framework_program_has_unresolved_dependencies",
            "framework": adapter.framework_id,
            "profile": profile,
            "unresolved_dependencies": dependency_state.unresolved,
            "compiled_calls": compiled_calls,
        }
    missing_required = _missing_required_arguments(compiled_calls, tool_schemas)
    if missing_required:
        return {
            "ok": False,
            "error": "framework_program_missing_required_arguments",
            "framework": adapter.framework_id,
            "profile": profile,
            "missing_arguments": missing_required,
            "compiled_calls": compiled_calls,
        }
    detail = language_tool_detail([call["tool"] for call in compiled_calls], detail="compact")
    mutating = [
        tool
        for tool in detail.get("tools", [])
        if isinstance(tool, dict) and not bool(tool.get("read_only"))
    ]
    return {
        "ok": True,
        "framework": adapter.framework_id,
        "profile": profile,
        "objective": parsed.objective,
        "mode": "preview",
        "compiled_calls": compiled_calls,
        "unresolved_intents": unresolved,
        "unresolved_dependencies": dependency_state.unresolved,
        "approval_required": bool(mutating),
        "validation_plan": [
            "Review compiled calls before execution.",
            "Execute mutating calls only after user approval.",
            "Refresh profile cache after successful writes.",
            "Verify the requested outcome from refreshed Bubble context.",
            "Call bubble_framework_sync_evidence with preview, execution, and validation evidence.",
        ],
        "next_action": "Preview or execute the compiled calls through MCP tools; do not bypass MCP safety gates.",
    }
