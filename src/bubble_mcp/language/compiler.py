"""Compile compact framework programs into preview-safe MCP calls."""

from __future__ import annotations

from typing import Any

from bubble_mcp.frameworks.adapters import get_adapter
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

INTENT_TOOL_ALIASES = {
    "create_group": "create_group",
    "create_container": "create_group",
    "create_section": "create_group",
    "create_card": "create_group",
    "create_text": "create_text",
    "add_text": "create_text",
    "headline": "create_text",
    "create_heading": "create_text",
    "create_button": "create_button",
    "add_button": "create_button",
    "cta_button": "create_button",
    "create_cta": "create_button",
    "create_input": "create_input",
    "add_input": "create_input",
    "text_input": "create_input",
    "verify_context": "bubble_context_find",
    "sync_evidence": "bubble_framework_sync_evidence",
    "query_language": "bubble_language_query",
    "find_tool": "bubble_language_query",
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


def _step_arguments(step: dict[str, Any]) -> dict[str, Any]:
    ignored = {"intent", "tool", "description", "arguments"}
    args = {str(key): value for key, value in step.items() if key not in ignored}
    raw_arguments = step.get("arguments")
    if isinstance(raw_arguments, dict):
        args.update(raw_arguments)
    return args


def _copy_first_available(args: dict[str, Any], target: str, candidates: tuple[str, ...]) -> None:
    if args.get(target) not in (None, ""):
        return
    for candidate in candidates:
        value = args.get(candidate)
        if value not in (None, ""):
            args[target] = value
            return


def _normalize_args_for_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    if tool_name == "create_text":
        _copy_first_available(normalized, "content", ("text", "label", "title", "name"))
    elif tool_name == "create_button":
        _copy_first_available(normalized, "label", ("text", "content", "title", "name"))
    elif tool_name in {"create_group", "create_input"}:
        _copy_first_available(normalized, "name", ("label", "title", "text", "content"))
    elif tool_name == "bubble_context_find":
        _copy_first_available(normalized, "query", ("target", "selector", "description", "name"))
        if "include_metadata" not in normalized:
            normalized["include_metadata"] = False
        if "limit" not in normalized:
            normalized["limit"] = 5
    elif tool_name == "bubble_language_query":
        _copy_first_available(normalized, "query", ("target", "selector", "description", "name"))
        if "limit" not in normalized:
            normalized["limit"] = 8
    elif tool_name == "bubble_framework_sync_evidence":
        if "evidence" not in normalized:
            evidence = normalized.get("result") or normalized.get("summary") or normalized.get("description")
            if evidence not in (None, ""):
                normalized["evidence"] = evidence
    return normalized


def _compile_intent_step(
    step: dict[str, Any],
    profile: str,
    framework_id: str,
    tool_schemas: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    intent = str(step.get("intent") or "")
    if intent == "resolve_context":
        args = _normalize_args_for_tool("bubble_context_find", _step_arguments(step))
        return {
            "tool": "bubble_context_find",
            "arguments": {
                "profile": profile,
                "query": str(args.get("query") or ""),
                "limit": int(args.get("limit") or 5),
                "include_metadata": bool(args.get("include_metadata", False)),
            },
        }
    if intent == "refresh_context":
        return {"tool": "bubble_profile_cache_refresh", "arguments": {"profile": profile, "force": True}}
    tool_name = INTENT_TOOL_ALIASES.get(intent)
    if tool_name:
        raw_args = _step_arguments(step)
        if tool_name == "bubble_framework_sync_evidence":
            raw_args.setdefault("framework", str(step.get("framework") or framework_id))
        args = _normalize_args_for_tool(tool_name, raw_args)
        return {
            "tool": tool_name,
            "arguments": _with_profile_and_preview(tool_name, args, profile, tool_schemas.get(tool_name)),
        }
    return {
        "tool": "bubble_tool_search",
        "arguments": {"query": intent or str(step.get("description") or ""), "limit": 8},
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


def compile_framework_program(
    *,
    framework: str,
    profile: str,
    program: dict[str, Any],
) -> dict[str, Any]:
    adapter = get_adapter(framework)
    if not isinstance(program, dict):
        raise ValueError("framework program must be an object.")
    raw_steps = program.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    tool_schemas = _available_tool_schemas()
    available = set(tool_schemas)
    compiled_calls: list[dict[str, Any]] = []
    unavailable: list[str] = []
    unresolved: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("tool"):
            tool_name = str(step.get("tool") or "")
            if tool_name not in available:
                unavailable.append(tool_name)
                continue
            raw_args = step.get("arguments")
            args = raw_args if isinstance(raw_args, dict) else {}
            normalized_args = _normalize_args_for_tool(tool_name, args)
            compiled_calls.append(
                {
                    "tool": tool_name,
                    "arguments": _with_profile_and_preview(
                        tool_name,
                        normalized_args,
                        profile,
                        tool_schemas.get(tool_name),
                    ),
                }
            )
        else:
            compiled = _compile_intent_step(step, profile, adapter.framework_id, tool_schemas)
            if compiled["tool"] not in available:
                unavailable.append(str(compiled["tool"]))
                continue
            if compiled.get("unresolved_intent"):
                unresolved.append(str(compiled["unresolved_intent"]))
                compiled.pop("unresolved_intent", None)
            compiled_calls.append(compiled)
    if unavailable:
        return {
            "ok": False,
            "error": "framework_program_has_unavailable_tools",
            "framework": adapter.framework_id,
            "profile": profile,
            "unavailable_tools": sorted(unavailable),
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
        "objective": str(program.get("objective") or ""),
        "mode": "preview",
        "compiled_calls": compiled_calls,
        "unresolved_intents": unresolved,
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
