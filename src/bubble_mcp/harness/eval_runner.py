"""Run deterministic planning evals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.validators.semantic import validate_plan


def load_dataset(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Eval dataset must be a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _args_match(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def estimate_tokens(payload: Any) -> int:
    """Cheap deterministic token estimate for comparing plan compactness."""

    return max(1, len(json.dumps(payload, separators=(",", ":"), sort_keys=True)) // 4)


def run_eval(dataset_path: Path, *, app_id: str | None = None, compile_plans: bool = False) -> dict[str, Any]:
    cases = load_dataset(dataset_path)
    results: list[dict[str, Any]] = []
    for case in cases:
        message = str(case.get("message") or "")
        expected_tool = str(case.get("expected_tool") or "")
        raw_expected_args = case.get("expected_args")
        expected_args: dict[str, Any] = raw_expected_args if isinstance(raw_expected_args, dict) else {}
        plan = plan_message(message).to_dict()
        first_step = plan["steps"][0] if plan["steps"] else {}
        compiled = False
        if compile_plans:
            target_app_id = app_id or str(case.get("app_id") or "synthetic-app")
            plan = compile_plan_to_write_payloads(plan, app_id=target_app_id)
            compiled = True
        validation = validate_plan(plan)
        tool_ok = bool(first_step) and first_step.get("tool_name") == expected_tool
        current_first_step = plan["steps"][0] if plan["steps"] else {}
        current_args = current_first_step.get("args", {}) if isinstance(current_first_step, dict) else {}
        args_ok = bool(current_first_step) and _args_match(current_args, expected_args)
        has_write_payload = isinstance(current_args, dict) and isinstance(current_args.get("write_payload"), dict)
        expected_compilable = bool(case.get("expected_compilable", compile_plans))
        compile_ok = (not expected_compilable) or has_write_payload
        passed = tool_ok and args_ok and validation["ok"] and compile_ok
        results.append(
            {
                "id": case.get("id"),
                "message": message,
                "passed": passed,
                "tool_ok": tool_ok,
                "args_ok": args_ok,
                "compile_ok": compile_ok,
                "compiled": compiled,
                "has_write_payload": has_write_payload,
                "validation_ok": validation["ok"],
                "tool_name": current_first_step.get("tool_name") if isinstance(current_first_step, dict) else None,
                "step_count": len(plan.get("steps", [])),
                "estimated_tokens": estimate_tokens(plan),
            }
        )

    return {
        "summary": {
            "cases": len(results),
            "passed": sum(1 for result in results if result["passed"]),
            "tool_ok": sum(1 for result in results if result["tool_ok"]),
            "args_ok": sum(1 for result in results if result["args_ok"]),
            "compile_ok": sum(1 for result in results if result["compile_ok"]),
            "validation_ok": sum(1 for result in results if result["validation_ok"]),
            "estimated_tokens": sum(int(result["estimated_tokens"]) for result in results),
        },
        "results": results,
        "failures": [result for result in results if not result["passed"]],
    }
