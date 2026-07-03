"""Operation state snapshots for agent harnesses."""

from __future__ import annotations

from typing import Any, cast

from bubble_mcp.core.redaction import redact_sensitive


def next_user_action(
    validation: dict[str, Any],
    *,
    execute: bool = False,
    has_session: bool = True,
) -> str:
    if not has_session and execute:
        return "capture_or_import_bubble_session"
    errors = [str(error) for error in validation.get("errors", []) if str(error).strip()]
    if any("no write_payload" in error for error in errors):
        return "compile_plan_before_execution"
    if any("destructive" in error for error in errors):
        return "request_user_confirmation"
    if errors:
        return "repair_plan"
    if not execute:
        return "review_preview_or_execute"
    return "inspect_editor_result"


def operation_snapshot(
    *,
    plan: dict[str, Any],
    validation: dict[str, Any],
    profile: str | None = None,
    execute: bool = False,
    phase: str = "planned",
    context_source: str | None = None,
    has_session: bool = True,
) -> dict[str, Any]:
    steps = plan.get("steps") if isinstance(plan, dict) else []
    step_summaries: list[dict[str, Any]] = []
    if isinstance(steps, list):
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            args = step.get("args") if isinstance(step.get("args"), dict) else {}
            step_summaries.append(
                {
                    "id": str(step.get("id") or f"step_{index + 1}"),
                    "tool_name": str(step.get("tool_name") or ""),
                    "has_write_payload": isinstance(args.get("write_payload") or args.get("payload"), dict)
                    if isinstance(args, dict)
                    else False,
                    "depends_on": step.get("depends_on") or step.get("dependsOn") or [],
                }
            )
    snapshot = {
        "phase": phase,
        "profile": profile,
        "execute": execute,
        "context_source": context_source,
        "step_count": len(step_summaries),
        "steps": step_summaries,
        "validation": validation,
        "next_user_action": next_user_action(validation, execute=execute, has_session=has_session),
    }
    return cast(dict[str, Any], redact_sensitive(snapshot))
