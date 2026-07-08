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
}


def _available_tool_names() -> set[str]:
    return {str(tool.get("name") or "") for tool in list_tool_schemas()}


def _with_profile_and_preview(tool_name: str, args: dict[str, Any], profile: str) -> dict[str, Any]:
    compiled = dict(args)
    if profile and "profile" not in compiled:
        compiled["profile"] = profile
    if tool_name not in READ_ONLY_TOOLS:
        compiled["execute"] = False
    return compiled


def _compile_intent_step(step: dict[str, Any], profile: str) -> dict[str, Any]:
    intent = str(step.get("intent") or "")
    if intent == "resolve_context":
        return {
            "tool": "bubble_context_find",
            "arguments": {
                "profile": profile,
                "query": str(step.get("query") or step.get("target") or ""),
                "limit": int(step.get("limit") or 5),
                "include_metadata": False,
            },
        }
    if intent == "refresh_context":
        return {"tool": "bubble_profile_cache_refresh", "arguments": {"profile": profile, "force": True}}
    return {
        "tool": "bubble_tool_search",
        "arguments": {"query": intent or str(step.get("description") or ""), "limit": 8},
        "unresolved_intent": intent,
    }


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
    available = _available_tool_names()
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
            compiled_calls.append({"tool": tool_name, "arguments": _with_profile_and_preview(tool_name, args, profile)})
        else:
            compiled = _compile_intent_step(step, profile)
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
