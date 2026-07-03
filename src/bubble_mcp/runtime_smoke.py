"""Operational smoke harness for MCP runtime coverage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any
from uuid import uuid4

from bubble_mcp.core.redaction import redact_sensitive


ToolCaller = Callable[[str, dict[str, Any]], dict[str, Any]]
RUNTIME_SMOKE_SUITES = {"coverage", "safe-read", "preview-write", "execute-write"}


@dataclass(frozen=True)
class SmokeCase:
    tool: str
    arguments: dict[str, Any]
    suite: str
    description: str
    requires_profile: bool = False


def _preview_name(prefix: str) -> str:
    return f"{prefix}_mcp_runtime_preview"


def _default_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"


def _safe_run_id(run_id: str = "") -> str:
    value = run_id.strip() or _default_run_id()
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:40] or _default_run_id()


def build_runtime_smoke_cases(
    *,
    profile: str = "",
    context: str = "index",
    parent: str = "root",
    app_id: str = "",
    app_version: str = "test",
    suite: str = "coverage",
    html_url: str = "",
    selector: str = "",
    execute: bool = False,
    cleanup: bool = False,
    run_id: str = "",
) -> list[SmokeCase]:
    """Build deterministic smoke cases for the requested suite."""

    effective_run_id = _safe_run_id(run_id)
    cases: list[SmokeCase] = [
        SmokeCase("bubble_tool_coverage", {}, "coverage", "Verify catalog execution coverage is complete."),
    ]

    if suite in {"coverage"}:
        return cases

    safe_read_cases = [
        SmokeCase("bubble_health_check", {}, "safe-read", "Read server capability metadata."),
        SmokeCase("bubble_profile_list", {}, "safe-read", "Read configured profiles."),
        SmokeCase("bubble_session_list", {}, "safe-read", "Read stored session metadata."),
    ]
    cases.extend(safe_read_cases)

    if profile:
        profile_args = {"profile": profile}
        if app_id:
            profile_args["app_id"] = app_id
        profile_args_with_json = {**profile_args, "json": True}
        cases.extend(
            [
                SmokeCase("list_data_types", dict(profile_args_with_json), "safe-read", "List Bubble data types.", True),
                SmokeCase("list_styles", dict(profile_args), "safe-read", "List Bubble styles.", True),
                SmokeCase("list_colors", dict(profile_args_with_json), "safe-read", "List Bubble colors.", True),
                SmokeCase("list_fonts", dict(profile_args_with_json), "safe-read", "List Bubble fonts.", True),
                SmokeCase("list_project_settings", dict(profile_args_with_json), "safe-read", "List Bubble project settings.", True),
            ]
        )

    if suite in {"safe-read"}:
        return cases

    if profile:
        is_execute_write = suite == "execute-write"
        mutation_suite = "execute-write" if is_execute_write else "preview-write"
        mutation_execute = bool(execute and is_execute_write)
        page_name = f"mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("page")
        target_context = page_name if is_execute_write else context
        target_parent = "root" if is_execute_write else parent
        base = {
            "profile": profile,
            "context": target_context,
            "parent": target_parent,
            "app_version": app_version,
            "execute": mutation_execute,
        }
        if app_id:
            base["app_id"] = app_id
        cases.extend(
            [
                SmokeCase(
                    "create_page",
                    {
                        "profile": profile,
                        "name": page_name,
                        "app_version": app_version,
                        "execute": mutation_execute,
                        **({"app_id": app_id} if app_id else {}),
                    },
                    mutation_suite,
                    "Execute page creation through the Aria runtime."
                    if is_execute_write
                    else "Preview page creation through the Aria runtime.",
                    True,
                ),
                SmokeCase(
                    "create_group",
                    {
                        **base,
                        "name": f"gp_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("gp"),
                        "layout": "column",
                        "min_height": "40px",
                        "fit_height": True,
                    },
                    mutation_suite,
                    "Execute group creation through the Aria runtime."
                    if is_execute_write
                    else "Preview group creation through the Aria runtime.",
                    True,
                ),
                SmokeCase(
                    "create_text",
                    {
                        **base,
                        "name": f"tx_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("tx"),
                        "content": f"Runtime smoke {effective_run_id}" if is_execute_write else "Runtime smoke preview",
                        "fit_height": True,
                    },
                    mutation_suite,
                    "Execute text creation with default fit-height behavior."
                    if is_execute_write
                    else "Preview text creation with default fit-height behavior.",
                    True,
                ),
                SmokeCase(
                    "create_button",
                    {
                        **base,
                        "name": f"bt_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("bt"),
                        "label": "Runtime smoke",
                        "fit_width": True,
                        "fit_height": True,
                    },
                    mutation_suite,
                    "Execute button creation with responsive sizing defaults."
                    if is_execute_write
                    else "Preview button creation with responsive sizing defaults.",
                    True,
                ),
                SmokeCase(
                    "create_input",
                    {
                        **base,
                        "name": f"in_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("in"),
                        "placeholder": "Runtime smoke",
                        "fixed_height": True,
                    },
                    mutation_suite,
                    "Execute input creation." if is_execute_write else "Preview input creation.",
                    True,
                ),
            ]
        )
        if html_url:
            cases.append(
                SmokeCase(
                    "create_from_html",
                    {
                        **base,
                        "url": html_url,
                        "selector": selector,
                        "rendered_html": True,
                        "refresh_context": False,
                    },
                    mutation_suite,
                    "Execute advanced HTML import through the packaged runtime."
                    if is_execute_write
                    else "Preview advanced HTML import through the packaged runtime.",
                    True,
                )
            )
        if is_execute_write and cleanup:
            cases.append(
                SmokeCase(
                    "delete_page",
                    {
                        "profile": profile,
                        "name": page_name,
                        "app_version": app_version,
                        "execute": True,
                        "confirm": True,
                        **({"app_id": app_id} if app_id else {}),
                    },
                    "execute-write",
                    "Clean up the temporary runtime smoke page.",
                    True,
                )
            )

    return cases


def _compact_result(result: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    if include_details:
        return redact_sensitive(result)
    compact: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "engine": result.get("engine"),
        "executed": result.get("executed"),
        "compiled": result.get("compiled"),
        "write_count": result.get("write_count"),
        "error": result.get("error"),
        "reason": result.get("reason"),
    }
    return {key: value for key, value in compact.items() if value is not None}


def run_runtime_smoke(
    tool_caller: ToolCaller,
    *,
    profile: str = "",
    context: str = "index",
    parent: str = "root",
    app_id: str = "",
    app_version: str = "test",
    suite: str = "coverage",
    limit: int = 0,
    html_url: str = "",
    selector: str = "",
    include_details: bool = False,
    stop_on_failure: bool = False,
    execute: bool = False,
    cleanup: bool = False,
    run_id: str = "",
) -> dict[str, Any]:
    """Run an operational smoke suite by calling MCP tool handlers."""

    if suite not in RUNTIME_SMOKE_SUITES:
        raise ValueError("suite must be one of: coverage, safe-read, preview-write, execute-write.")
    effective_run_id = _safe_run_id(run_id)
    if suite == "execute-write" and not execute:
        return {
            "ok": False,
            "suite": suite,
            "profile": profile or None,
            "context": context,
            "parent": parent,
            "app_id": app_id or None,
            "app_version": app_version,
            "execute": False,
            "cleanup": cleanup,
            "run_id": effective_run_id,
            "error": "execute-write requires execute=true.",
            "summary": {"cases": 0, "passed": 0, "failed": 1, "skipped": 0},
            "results": [],
        }
    cases = build_runtime_smoke_cases(
        profile=profile,
        context=context,
        parent=parent,
        app_id=app_id,
        app_version=app_version,
        suite=suite,
        html_url=html_url,
        selector=selector,
        execute=execute,
        cleanup=cleanup,
        run_id=effective_run_id,
    )
    if limit > 0:
        cases = cases[:limit]

    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if case.requires_profile and not profile:
            results.append(
                {
                    "index": index,
                    "tool": case.tool,
                    "suite": case.suite,
                    "status": "skipped",
                    "ok": True,
                    "reason": "profile_required",
                    "description": case.description,
                }
            )
            continue
        try:
            result = tool_caller(case.tool, dict(case.arguments))
            case_ok = bool(result.get("ok"))
            results.append(
                {
                    "index": index,
                    "tool": case.tool,
                    "suite": case.suite,
                    "status": "passed" if case_ok else "failed",
                    "ok": case_ok,
                    "description": case.description,
                    "result": _compact_result(result, include_details=include_details),
                }
            )
        except Exception as exc:  # noqa: BLE001 - smoke reports must capture failures.
            results.append(
                {
                    "index": index,
                    "tool": case.tool,
                    "suite": case.suite,
                    "status": "failed",
                    "ok": False,
                    "description": case.description,
                    "error": str(exc),
                }
            )
        if stop_on_failure and results[-1]["status"] == "failed":
            break

    summary = {
        "cases": len(results),
        "passed": sum(1 for item in results if item["status"] == "passed"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
    }
    return {
        "ok": summary["failed"] == 0,
        "suite": suite,
        "profile": profile or None,
        "context": context,
        "parent": parent,
        "app_id": app_id or None,
        "app_version": app_version,
        "execute": bool(execute and suite == "execute-write"),
        "cleanup": bool(cleanup and suite == "execute-write"),
        "run_id": effective_run_id,
        "summary": summary,
        "results": results,
    }
