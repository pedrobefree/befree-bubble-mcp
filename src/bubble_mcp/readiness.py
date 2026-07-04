"""Composite readiness checks for local Bubble MCP installs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


ToolCaller = Callable[[str, dict[str, Any]], dict[str, Any]]


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"ok": bool(result.get("ok"))}
    for key in ("version", "suite", "summary", "error"):
        if key in result:
            summary[key] = result[key]
    if "capabilities" in result and isinstance(result["capabilities"], dict):
        summary["capabilities"] = {
            key: result["capabilities"][key]
            for key in sorted(result["capabilities"])
            if key
            in {
                "profiles",
                "session_capture",
                "context_engine",
                "planner",
                "html_import",
                "mutations",
                "aria_runtime_dispatch",
            }
        }
    return summary


def _check_result(name: str, result: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    check = {
        "name": name,
        "ok": bool(result.get("ok")),
        "summary": _result_summary(result),
    }
    if include_details:
        check["result"] = result
    return check


def run_readiness_check(
    tool_caller: ToolCaller,
    *,
    profile: str = "",
    context: str = "index",
    parent: str = "root",
    app_id: str = "",
    app_version: str = "test",
    include_family_preview: bool = False,
    include_details: bool = False,
    stop_on_failure: bool = False,
) -> dict[str, Any]:
    """Run the compact readiness sequence agents should use before broad work."""

    checks: list[dict[str, Any]] = []

    def run(name: str, tool: str, args: dict[str, Any]) -> bool:
        result = tool_caller(tool, args)
        checks.append(_check_result(name, result, include_details=include_details))
        return bool(result.get("ok"))

    sequence: list[tuple[str, str, dict[str, Any]]] = [
        ("health", "bubble_health_check", {}),
        ("catalog_gate", "bubble_runtime_smoke", {"suite": "coverage"}),
        ("agent_routing", "bubble_runtime_smoke", {"suite": "agent-routing"}),
    ]

    profile_args = {
        "profile": profile,
        "context": context,
        "parent": parent,
        "app_id": app_id,
        "app_version": app_version,
    }
    if profile:
        sequence.append(("safe_read", "bubble_runtime_smoke", {**profile_args, "suite": "safe-read"}))
        if include_family_preview:
            sequence.append(
                (
                    "family_preview",
                    "bubble_runtime_smoke",
                    {**profile_args, "suite": "family-preview"},
                )
            )

    for name, tool, args in sequence:
        passed = run(name, tool, {key: value for key, value in args.items() if value not in ("", None)})
        if stop_on_failure and not passed:
            break

    failed = [check for check in checks if not check["ok"]]
    return {
        "ok": not failed,
        "profile": profile or None,
        "context": context,
        "parent": parent,
        "app_id": app_id or None,
        "app_version": app_version,
        "include_family_preview": include_family_preview,
        "include_details": include_details,
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
        },
        "checks": checks,
    }
