"""Execute Bubble plans through authenticated editor writes."""

from __future__ import annotations

from typing import Any

from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.context.source import load_context
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.sessions.store import BubbleSessionData, load_session


def extract_write_payload(step: dict[str, Any]) -> dict[str, Any] | None:
    raw_args = step.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
    candidate = args.get("write_payload") or args.get("payload") or step.get("write_payload")
    return candidate if isinstance(candidate, dict) else None


def execute_plan(
    plan: dict[str, Any],
    *,
    profile: str,
    execute: bool = False,
    app_id: str | None = None,
    app_version: str = "test",
    context: BubbleProjectContext | None = None,
    compile_missing: bool = False,
    auto_context: bool = True,
    session: BubbleSessionData | None = None,
    client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    if compile_missing:
        target_app_id = app_id or (session.app_id if session else None)
        if not target_app_id:
            loaded_for_app = load_session(profile)
            target_app_id = loaded_for_app.app_id if loaded_for_app else None
        if not target_app_id:
            raise ValueError("app_id is required when compile_missing is true.")
        context_source: str | None = None
        if context is None and auto_context and session is None:
            detected = detect_project_context(
                profile=profile,
                app_id=target_app_id,
                app_version=app_version,
            )
            context = load_context(detected.context_path)
            context_source = detected.source
        plan = compile_plan_to_write_payloads(
            plan,
            app_id=target_app_id,
            app_version=app_version,
            context=context,
        )
        if context_source:
            plan.setdefault("metadata", {})
            if isinstance(plan["metadata"], dict):
                plan["metadata"]["context_source"] = context_source

    steps = plan.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Plan must include a steps array.")

    resolved_session = session or load_session(profile)
    if execute and resolved_session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")

    editor_client = client or BubbleEditorClient()
    results: list[dict[str, Any]] = []

    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Plan step {index + 1} must be an object.")
        step_id = str(raw_step.get("id") or f"step_{index + 1}")
        payload = extract_write_payload(raw_step)
        if payload is None:
            results.append(
                {
                    "step_id": step_id,
                    "ok": not execute,
                    "executed": False,
                    "skipped": True,
                    "reason": "step_has_no_write_payload",
                    "tool_name": raw_step.get("tool_name"),
                }
            )
            if execute:
                break
            continue

        if not execute:
            results.append(
                {
                    "step_id": step_id,
                    "ok": True,
                    "executed": False,
                    "dry_run": True,
                    "payload": payload,
                }
            )
            continue

        assert resolved_session is not None
        write_result = editor_client.write(payload, resolved_session, dry_run=False)
        results.append(
            {
                "step_id": step_id,
                "ok": bool(write_result.get("ok")),
                "executed": True,
                "result": write_result,
            }
        )
        if not write_result.get("ok"):
            break

    return {
        "ok": all(bool(result.get("ok")) for result in results),
        "executed": execute,
        "profile": profile,
        "step_count": len(steps),
        "results": results,
        **(
            {"context_source": plan.get("metadata", {}).get("context_source")}
            if isinstance(plan.get("metadata"), dict) and plan["metadata"].get("context_source")
            else {}
        ),
    }
