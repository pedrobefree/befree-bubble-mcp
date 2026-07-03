"""Run deterministic planning evals."""

from __future__ import annotations

import json
from collections.abc import Iterable
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


def _first_present(case: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in case:
            return case[key]
    return default


def _dict_field(case: dict[str, Any], *keys: str) -> dict[str, Any]:
    value = _first_present(case, *keys, default={})
    return value if isinstance(value, dict) else {}


def _list_field(case: dict[str, Any], *keys: str) -> list[str]:
    value = _first_present(case, *keys, default=[])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _expected_tool(case: dict[str, Any]) -> str:
    return str(_first_present(case, "expected_tool", "expectedTool", default="") or "")


def _expected_compilable(case: dict[str, Any], compile_plans: bool) -> bool:
    return bool(_first_present(case, "expected_compilable", "expectedCompilable", default=compile_plans))


def _warnings_match(actual: Iterable[str], expected_includes: list[str]) -> bool:
    warnings = list(actual)
    return all(any(expected in warning for warning in warnings) for expected in expected_includes)


def _missing_ok(validation: dict[str, Any]) -> bool:
    errors = validation.get("errors")
    if not isinstance(errors, list):
        return False
    return not any("missing required args" in str(error) for error in errors)


def _fallback_reasons(
    *,
    matched: bool,
    tool_ok: bool,
    args_ok: bool,
    missing_ok: bool,
    validation_ok: bool,
    warnings_ok: bool,
    compile_ok: bool,
) -> list[str]:
    reasons: list[str] = []
    if not matched:
        return ["no_plan_steps"]
    if not tool_ok:
        reasons.append("tool_mismatch")
    if not args_ok:
        reasons.append("args_mismatch")
    if not missing_ok:
        reasons.append("missing_required_args")
    if not validation_ok:
        reasons.append("validation_failed")
    if not warnings_ok:
        reasons.append("warnings_mismatch")
    if not compile_ok:
        reasons.append("compile_missing_write_payload")
    return reasons


def estimate_tokens(payload: Any) -> int:
    """Cheap deterministic token estimate for comparing plan compactness."""

    return max(1, len(json.dumps(payload, separators=(",", ":"), sort_keys=True)) // 4)


def run_eval(dataset_path: Path, *, app_id: str | None = None, compile_plans: bool = False) -> dict[str, Any]:
    cases = load_dataset(dataset_path)
    results: list[dict[str, Any]] = []
    for case in cases:
        message = str(case.get("message") or "")
        expected_tool = _expected_tool(case)
        expected_args = _dict_field(case, "expected_args", "expectedArgs")
        expected_warnings = _list_field(case, "expected_warnings_includes", "expectedWarningsIncludes")
        plan = plan_message(message).to_dict()
        first_step = plan["steps"][0] if plan["steps"] else {}
        matched = bool(first_step)
        compiled = False
        if compile_plans:
            target_app_id = app_id or str(case.get("app_id") or "synthetic-app")
            plan = compile_plan_to_write_payloads(plan, app_id=target_app_id)
            compiled = True
        validation = validate_plan(plan)
        tool_ok = bool(first_step) and (not expected_tool or first_step.get("tool_name") == expected_tool)
        current_first_step = plan["steps"][0] if plan["steps"] else {}
        current_args = current_first_step.get("args", {}) if isinstance(current_first_step, dict) else {}
        args_ok = bool(current_first_step) and _args_match(current_args, expected_args)
        has_write_payload = isinstance(current_args, dict) and isinstance(current_args.get("write_payload"), dict)
        expected_compilable = _expected_compilable(case, compile_plans)
        compile_ok = (not expected_compilable) or has_write_payload
        plan_warnings = [str(warning) for warning in plan.get("warnings", []) if str(warning).strip()]
        validation_warnings = [
            str(warning)
            for warning in validation.get("warnings", [])
            if str(warning).strip()
        ]
        warnings = sorted(set([*plan_warnings, *validation_warnings]))
        warnings_ok = _warnings_match(warnings, expected_warnings)
        validation_ok = bool(validation["ok"])
        missing_ok = _missing_ok(validation)
        fallback_reasons = _fallback_reasons(
            matched=matched,
            tool_ok=tool_ok,
            args_ok=args_ok,
            missing_ok=missing_ok,
            validation_ok=validation_ok,
            warnings_ok=warnings_ok,
            compile_ok=compile_ok,
        )
        passed = matched and tool_ok and args_ok and missing_ok and validation_ok and warnings_ok and compile_ok
        results.append(
            {
                "id": case.get("id"),
                "message": message,
                "passed": passed,
                "matched": matched,
                "expected_tool": expected_tool or None,
                "tool_ok": tool_ok,
                "args_ok": args_ok,
                "missing_ok": missing_ok,
                "warnings_ok": warnings_ok,
                "compile_ok": compile_ok,
                "compiled": compiled,
                "has_write_payload": has_write_payload,
                "validation_ok": validation_ok,
                "tool_name": current_first_step.get("tool_name") if isinstance(current_first_step, dict) else None,
                "parser": "deterministic" if matched else "none",
                "fallback_reason": fallback_reasons[0] if fallback_reasons else None,
                "fallback_reasons": fallback_reasons,
                "warnings": warnings,
                "validation_errors": [
                    str(error)
                    for error in validation.get("errors", [])
                    if str(error).strip()
                ],
                "step_count": len(plan.get("steps", [])),
                "estimated_tokens": estimate_tokens(plan),
            }
        )

    fallback_summary: dict[str, int] = {}
    parser_summary: dict[str, int] = {}
    for result in results:
        parser = str(result["parser"])
        parser_summary[parser] = parser_summary.get(parser, 0) + 1
        reasons = result.get("fallback_reasons")
        if isinstance(reasons, list):
            for reason in reasons or ["none"]:
                key = str(reason or "none")
                fallback_summary[key] = fallback_summary.get(key, 0) + 1
        else:
            key = str(result.get("fallback_reason") or "none")
            fallback_summary[key] = fallback_summary.get(key, 0) + 1

    return {
        "summary": {
            "cases": len(results),
            "passed": sum(1 for result in results if result["passed"]),
            "matched": sum(1 for result in results if result["matched"]),
            "tool_ok": sum(1 for result in results if result["tool_ok"]),
            "args_ok": sum(1 for result in results if result["args_ok"]),
            "missing_ok": sum(1 for result in results if result["missing_ok"]),
            "compile_ok": sum(1 for result in results if result["compile_ok"]),
            "validation_ok": sum(1 for result in results if result["validation_ok"]),
            "warnings_ok": sum(1 for result in results if result["warnings_ok"]),
            "estimated_tokens": sum(int(result["estimated_tokens"]) for result in results),
            "parser_summary": parser_summary,
            "fallback_summary": fallback_summary,
        },
        "results": results,
        "failures": [result for result in results if not result["passed"]],
    }
