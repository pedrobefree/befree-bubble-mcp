"""Execute Bubble plans through authenticated editor writes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.freshness import context_freshness, load_context_with_overlay
from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.context.mutation_overlay import record_mutation_overlay
from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.execution.executor_types import extract_write_payload
from bubble_mcp.execution.state import operation_snapshot
from bubble_mcp.execution.structural import validate_structure
from bubble_mcp.sessions.store import BubbleSessionData, load_session


def execute_plan(
    plan: dict[str, Any],
    *,
    profile: str,
    execute: bool = False,
    app_id: str | None = None,
    app_version: str | None = None,
    context: BubbleProjectContext | None = None,
    compile_missing: bool = False,
    auto_context: bool = True,
    session: BubbleSessionData | None = None,
    client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    resolved_session = session or load_session(profile)
    target_app_version = _resolve_target_app_version(
        profile=profile,
        app_version=app_version,
        session=resolved_session,
    )
    if compile_missing:
        target_app_id = app_id or (session.app_id if session else None)
        if not target_app_id:
            target_app_id = resolved_session.app_id if resolved_session else None
        if not target_app_id:
            raise ValueError("app_id is required when compile_missing is true.")
        context_source: str | None = None
        if context is None and auto_context and session is None:
            detected = detect_project_context(
                profile=profile,
                app_id=target_app_id,
                app_version=target_app_version,
            )
            context = load_context_with_overlay(
                detected.context_path,
                profile=profile,
                app_id=target_app_id,
            )
            context_source = detected.source
        plan = compile_plan_to_write_payloads(
            plan,
            app_id=target_app_id,
            app_version=target_app_version,
            context=context,
        )
        if context_source:
            plan.setdefault("metadata", {})
            if isinstance(plan["metadata"], dict):
                plan["metadata"]["context_source"] = context_source
                if context is not None:
                    plan["metadata"]["context_freshness"] = context_freshness(context)

    steps = plan.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Plan must include a steps array.")

    if execute and resolved_session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")

    structural_validation = validate_structure(plan, execute=execute)
    if execute and not structural_validation["ok"]:
        return {
            "ok": False,
            "executed": False,
            "profile": profile,
            "step_count": len(steps),
            "results": [],
            "structural_validation": structural_validation,
            "operation_snapshot": operation_snapshot(
                plan=plan,
                validation=structural_validation,
                profile=profile,
                execute=execute,
                phase="blocked",
                context_source=plan.get("metadata", {}).get("context_source")
                if isinstance(plan.get("metadata"), dict)
                else None,
                has_session=resolved_session is not None,
            ),
        }

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
        payload = _payload_with_target_version(payload, target_app_version)

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
        if write_result.get("ok"):
            record_mutation_overlay(
                profile=profile,
                app_id=str(payload.get("appname") or resolved_session.app_id or ""),
                payload=write_result.get("request", {}).get("payload") or payload,
                source="execute_plan",
                response=write_result.get("response"),
            )
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

    context_source = (
        plan.get("metadata", {}).get("context_source")
        if isinstance(plan.get("metadata"), dict) and plan["metadata"].get("context_source")
        else None
    )
    context_freshness_meta = (
        plan.get("metadata", {}).get("context_freshness")
        if isinstance(plan.get("metadata"), dict) and plan["metadata"].get("context_freshness")
        else None
    )
    result = {
        "ok": all(bool(result.get("ok")) for result in results),
        "executed": execute,
        "profile": profile,
        "step_count": len(steps),
        "results": results,
        "structural_validation": structural_validation,
        "operation_snapshot": operation_snapshot(
            plan=plan,
            validation=structural_validation,
            profile=profile,
            execute=execute,
            phase="executed" if execute else "previewed",
            context_source=str(context_source) if context_source else None,
            has_session=resolved_session is not None,
        ),
    }
    if context_source:
        result["context_source"] = context_source
    if context_freshness_meta:
        result["context_freshness"] = context_freshness_meta
    return result


def _resolve_target_app_version(
    *,
    profile: str,
    app_version: str | None,
    session: BubbleSessionData | None,
) -> str:
    explicit = str(app_version or "").strip()
    if explicit:
        return explicit
    configured_profile = resolve_profile(load_settings(), profile)
    return str(
        (configured_profile.app_version if configured_profile and configured_profile.app_version else "")
        or (session.app_version if session and session.app_version else "")
        or "test"
    ).strip()


def _payload_with_target_version(payload: dict[str, Any], app_version: str) -> dict[str, Any]:
    if not app_version:
        return payload
    targeted = deepcopy(payload)
    targeted["app_version"] = app_version
    if "appVersion" in targeted:
        targeted["appVersion"] = app_version
    return targeted
