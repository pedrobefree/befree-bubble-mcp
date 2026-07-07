"""Preview-first runner for executable Bubble MCP skills."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from bubble_mcp.skills.audit import load_run_record, new_run_id, save_run_record, utc_now_iso
from bubble_mcp.skills.store import get_skill
from bubble_mcp.skills.validator import validate_skill_file


INPUT_PATTERN = re.compile(r"^\{\{inputs\.([A-Za-z0-9_.-]+)\}\}$")


def _skill_payload(skill_id: str) -> tuple[dict[str, Any], str]:
    installed = get_skill(skill_id)
    if installed.state != "enabled":
        raise ValueError(f"Skill is not enabled: {skill_id}")
    report = validate_skill_file(installed.path)
    if not report.get("ok"):
        raise ValueError(f"Skill is invalid: {skill_id}: {report.get('errors')}")
    if not report.get("executable"):
        raise ValueError("skill_contract_not_executable")
    skill = report.get("skill")
    if not isinstance(skill, dict):
        raise ValueError(f"Skill validation did not return skill payload: {skill_id}")
    return skill, str(installed.path)


def _required_inputs(skill: dict[str, Any]) -> list[str]:
    inputs = skill.get("inputs")
    if not isinstance(inputs, dict):
        return []
    required: list[str] = []
    for name, schema in inputs.items():
        if isinstance(schema, dict) and schema.get("required") is True:
            required.append(str(name))
    return required


def _resolve_value(value: Any, inputs: dict[str, Any]) -> Any:
    if isinstance(value, str):
        match = INPUT_PATTERN.match(value)
        if match:
            return inputs.get(match.group(1))
        resolved = value
        for key, input_value in inputs.items():
            resolved = resolved.replace(f"{{{{inputs.{key}}}}}", str(input_value))
        return resolved
    if isinstance(value, list):
        return [_resolve_value(item, inputs) for item in value]
    if isinstance(value, dict):
        return {str(key): _resolve_value(child, inputs) for key, child in value.items()}
    return value


def _call_mcp_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    from bubble_mcp.server.tools import call_tool

    return call_tool(tool_name, args)


def _with_execute_flag(args: dict[str, Any], execute: bool) -> dict[str, Any]:
    updated = copy.deepcopy(args)
    if "execute" in updated:
        updated["execute"] = execute
    nested = updated.get("arguments")
    if isinstance(nested, dict) and "execute" in nested:
        nested["execute"] = execute
    return updated


def _plan_hash(plan: list[dict[str, Any]]) -> str:
    body = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _user_step_summary(step: dict[str, Any], *, status: str, error: str | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": step["id"],
        "action": step["action"],
        "tool": step["tool"],
        "mode": step["mode"],
        "status": status,
    }
    if step["mode"] in {"preview", "write"}:
        summary["risk"] = "mutating"
        summary["approval"] = "required"
    if error:
        summary["error"] = error
    return summary


def _build_plan(skill: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    raw_steps = skill.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    for raw_step in steps:
        if not isinstance(raw_step, dict):
            continue
        step_id = str(raw_step.get("id") or "")
        tool_name = str(raw_step.get("tool") or "")
        mode = str(raw_step.get("mode") or "read")
        args = _resolve_value(raw_step.get("args") if isinstance(raw_step.get("args"), dict) else {}, inputs)
        if mode in {"preview", "write"}:
            args = _with_execute_flag(args, False)
        plan.append(
            {
                "id": step_id,
                "action": str(raw_step.get("description") or tool_name),
                "tool": tool_name,
                "mode": mode,
                "args": args,
                "dependsOn": raw_step.get("dependsOn", []),
            }
        )
    return plan


def _validate_inputs(skill: dict[str, Any], inputs: dict[str, Any]) -> list[str]:
    return [name for name in _required_inputs(skill) if inputs.get(name) in (None, "")]


def run_skill(
    skill_id: str,
    *,
    inputs: dict[str, Any] | None = None,
    execute: bool = False,
    approve_execution: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    if execute:
        if not approve_execution:
            return {"ok": False, "error": "skill_execution_requires_approval", "approval_required": True}
        if not run_id:
            return {"ok": False, "error": "skill_execution_requires_preview_run", "approval_required": True}
        return _execute_approved_run(skill_id, run_id)
    return _preview_skill_run(skill_id, inputs or {})


def _preview_skill_run(skill_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    skill, skill_path = _skill_payload(skill_id)
    missing = _validate_inputs(skill, inputs)
    if missing:
        return {"ok": False, "error": "skill_missing_required_inputs", "missing": missing}
    plan = _build_plan(skill, inputs)
    steps: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    for step in plan:
        mode = str(step.get("mode") or "read")
        raw_args = step.get("args")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        status = "ready"
        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            if mode in {"read", "preview"}:
                result = _call_mcp_tool(str(step["tool"]), args)
            elif mode == "write":
                result = _call_mcp_tool(str(step["tool"]), _with_execute_flag(args, False))
        except Exception as exc:  # pragma: no cover - exercised through public error response
            status = "error"
            error = str(exc)
        tool_calls.append({"step_id": step["id"], "tool": step["tool"], "mode": mode, "args": args, "result": result})
        steps.append(_user_step_summary(step, status=status, error=error))
        if error:
            break
    run_id = new_run_id()
    plan_hash = _plan_hash(plan)
    record = {
        "run_id": run_id,
        "skill_id": skill_id,
        "skill_path": skill_path,
        "mode": "preview",
        "created_at": utc_now_iso(),
        "inputs": inputs,
        "plan": plan,
        "plan_hash": plan_hash,
        "tool_calls": tool_calls,
        "steps": steps,
    }
    audit_path = save_run_record(record)
    return {
        "ok": not any(step.get("status") == "error" for step in steps),
        "mode": "preview",
        "run_id": run_id,
        "skill_id": skill_id,
        "summary": f"Skill {skill_id} prepared {len(steps)} step(s).",
        "steps": steps,
        "approval_required": any(step.get("mode") in {"preview", "write"} for step in steps)
        or str(skill.get("risk")) in {"mutating", "destructive"},
        "audit_path": str(audit_path),
        "next_action": "Review the steps and call again with execute=true, approve_execution=true, and this run_id.",
    }


def _execute_approved_run(skill_id: str, run_id: str) -> dict[str, Any]:
    record = load_run_record(run_id)
    if record.get("skill_id") != skill_id:
        return {"ok": False, "error": "skill_run_skill_mismatch", "run_id": run_id}
    skill, _skill_path = _skill_payload(skill_id)
    plan = record.get("plan")
    if not isinstance(plan, list):
        return {"ok": False, "error": "skill_run_missing_plan", "run_id": run_id}
    if _plan_hash(plan) != record.get("plan_hash"):
        return {"ok": False, "error": "skill_run_plan_changed", "run_id": run_id}
    raw_allowed_tools = skill.get("allowedTools")
    allowed_tools = set(raw_allowed_tools if isinstance(raw_allowed_tools, list) else [])
    steps: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool") or "")
        mode = str(step.get("mode") or "read")
        if tool_name not in allowed_tools:
            return {"ok": False, "error": "skill_step_tool_not_allowed", "tool": tool_name, "run_id": run_id}
        raw_args = step.get("args")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        if mode == "write":
            args = _with_execute_flag(args, True)
        status = "executed"
        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            result = _call_mcp_tool(tool_name, args)
        except Exception as exc:  # pragma: no cover - exercised through public error response
            status = "error"
            error = str(exc)
        tool_calls.append({"step_id": step.get("id"), "tool": tool_name, "mode": mode, "args": args, "result": result})
        steps.append(_user_step_summary(step, status=status, error=error))
        if error:
            break
    executed_record = {
        **record,
        "mode": "executed",
        "executed_at": utc_now_iso(),
        "execution_tool_calls": tool_calls,
        "execution_steps": steps,
    }
    audit_path = save_run_record(executed_record)
    return {
        "ok": not any(step.get("status") == "error" for step in steps),
        "mode": "executed",
        "run_id": run_id,
        "skill_id": skill_id,
        "summary": f"Skill {skill_id} executed {len(steps)} approved step(s).",
        "steps": steps,
        "audit_path": str(audit_path),
    }
