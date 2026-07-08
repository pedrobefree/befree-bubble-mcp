"""Preview and execute local Bubble transfer plans."""

from __future__ import annotations

from typing import Any

from bubble_mcp.context.mutation_overlay import record_mutation_overlay
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.sessions.store import load_session
from bubble_mcp.transfer.store import load_transfer_plan


def _payloads(plan: dict[str, Any]) -> list[dict[str, Any]]:
    payloads = plan.get("write_payloads")
    if not isinstance(payloads, list):
        raise ValueError("Transfer plan is missing write_payloads.")
    return [payload for payload in payloads if isinstance(payload, dict)]


def preview_transfer_plan(
    transfer_id: str,
    *,
    include_payloads: bool = False,
    client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    """Dry-run planned payloads against the target session."""

    plan = load_transfer_plan(transfer_id)
    blocked = plan.get("blocked_reasons")
    if isinstance(blocked, list) and blocked:
        return {"ok": False, "transfer_id": transfer_id, "blocked_reasons": blocked, "payload_count": 0}
    target_profile = str(plan.get("target_profile") or "")
    session = load_session(target_profile)
    if session is None:
        raise ValueError(f"No Bubble session stored for target profile '{target_profile}'.")
    editor_client = client or BubbleEditorClient()
    results = [
        editor_client.write(payload, session, dry_run=True)
        for payload in _payloads(plan)
    ]
    return {
        "ok": all(bool(item.get("ok")) for item in results),
        "transfer_id": transfer_id,
        "target_profile": target_profile,
        "payload_count": len(results),
        "results": results if include_payloads else [{"ok": item.get("ok"), "dry_run": item.get("dry_run")} for item in results],
    }


def execute_transfer_plan(
    transfer_id: str,
    *,
    execute: bool,
    confirm: bool,
    max_steps: int | None = None,
    client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    """Execute a reviewed transfer plan against the target profile."""

    if not execute:
        raise ValueError("bubble_transfer_execute requires execute=true.")
    if not confirm:
        raise ValueError("bubble_transfer_execute requires confirm=true.")

    plan = load_transfer_plan(transfer_id)
    blocked = plan.get("blocked_reasons")
    if isinstance(blocked, list) and blocked:
        return {"ok": False, "executed": False, "transfer_id": transfer_id, "blocked_reasons": blocked}

    target_profile = str(plan.get("target_profile") or "")
    session = load_session(target_profile)
    if session is None:
        raise ValueError(f"No Bubble session stored for target profile '{target_profile}'.")

    payloads = _payloads(plan)
    limited = payloads[:max_steps] if max_steps else payloads
    editor_client = client or BubbleEditorClient()
    results: list[dict[str, Any]] = []
    for payload in limited:
        result = editor_client.write(payload, session, dry_run=False)
        if result.get("ok"):
            request_payload = result.get("request", {}).get("payload") if isinstance(result.get("request"), dict) else None
            record_mutation_overlay(
                profile=target_profile,
                app_id=str(payload.get("appname") or session.app_id),
                payload=request_payload if isinstance(request_payload, dict) else payload,
                source="bubble_transfer_execute",
                response=result.get("response"),
            )
        results.append({"ok": bool(result.get("ok")), "result": result})
        if not result.get("ok"):
            break
    return {
        "ok": all(item.get("ok") for item in results),
        "executed": True,
        "transfer_id": transfer_id,
        "target_profile": target_profile,
        "result_count": len(results),
        "results": results,
    }
