"""Run deterministic planning evals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.validators.semantic import validate_plan


def load_dataset(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Eval dataset must be a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _args_match(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def run_eval(dataset_path: Path) -> dict[str, Any]:
    cases = load_dataset(dataset_path)
    results: list[dict[str, Any]] = []
    for case in cases:
        message = str(case.get("message") or "")
        expected_tool = str(case.get("expected_tool") or "")
        raw_expected_args = case.get("expected_args")
        expected_args: dict[str, Any] = raw_expected_args if isinstance(raw_expected_args, dict) else {}
        plan = plan_message(message).to_dict()
        first_step = plan["steps"][0] if plan["steps"] else {}
        validation = validate_plan(plan)
        tool_ok = bool(first_step) and first_step.get("tool_name") == expected_tool
        args_ok = bool(first_step) and _args_match(first_step.get("args", {}), expected_args)
        passed = tool_ok and args_ok and validation["ok"]
        results.append(
            {
                "id": case.get("id"),
                "message": message,
                "passed": passed,
                "tool_ok": tool_ok,
                "args_ok": args_ok,
                "validation_ok": validation["ok"],
                "tool_name": first_step.get("tool_name"),
            }
        )

    return {
        "summary": {
            "cases": len(results),
            "passed": sum(1 for result in results if result["passed"]),
            "tool_ok": sum(1 for result in results if result["tool_ok"]),
            "args_ok": sum(1 for result in results if result["args_ok"]),
            "validation_ok": sum(1 for result in results if result["validation_ok"]),
        },
        "results": results,
        "failures": [result for result in results if not result["passed"]],
    }
