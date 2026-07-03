"""Operational smoke harness for MCP runtime coverage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bubble_mcp.core.redaction import redact_sensitive


ToolCaller = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SmokeCase:
    tool: str
    arguments: dict[str, Any]
    suite: str
    description: str
    requires_profile: bool = False


def _preview_name(prefix: str) -> str:
    return f"{prefix}_mcp_runtime_preview"


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
) -> list[SmokeCase]:
    """Build deterministic smoke cases for the requested suite."""

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
        base = {
            "profile": profile,
            "context": context,
            "parent": parent,
            "app_version": app_version,
            "execute": False,
        }
        if app_id:
            base["app_id"] = app_id
        cases.extend(
            [
                SmokeCase(
                    "create_page",
                    {
                        "profile": profile,
                        "name": _preview_name("page"),
                        "app_version": app_version,
                        "execute": False,
                        **({"app_id": app_id} if app_id else {}),
                    },
                    "preview-write",
                    "Preview page creation through the Aria runtime.",
                    True,
                ),
                SmokeCase(
                    "create_group",
                    {**base, "name": _preview_name("gp"), "layout": "column", "min_height": "40px", "fit_height": True},
                    "preview-write",
                    "Preview group creation through the Aria runtime.",
                    True,
                ),
                SmokeCase(
                    "create_text",
                    {**base, "name": _preview_name("tx"), "content": "Runtime smoke preview", "fit_height": True},
                    "preview-write",
                    "Preview text creation with default fit-height behavior.",
                    True,
                ),
                SmokeCase(
                    "create_button",
                    {**base, "name": _preview_name("bt"), "label": "Runtime smoke", "fit_width": True, "fit_height": True},
                    "preview-write",
                    "Preview button creation with responsive sizing defaults.",
                    True,
                ),
                SmokeCase(
                    "create_input",
                    {**base, "name": _preview_name("in"), "placeholder": "Runtime smoke", "fixed_height": True},
                    "preview-write",
                    "Preview input creation.",
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
                    "preview-write",
                    "Preview advanced HTML import through the packaged runtime.",
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
) -> dict[str, Any]:
    """Run an operational smoke suite by calling MCP tool handlers."""

    if suite not in {"coverage", "safe-read", "preview-write"}:
        raise ValueError("suite must be one of: coverage, safe-read, preview-write.")
    cases = build_runtime_smoke_cases(
        profile=profile,
        context=context,
        parent=parent,
        app_id=app_id,
        app_version=app_version,
        suite=suite,
        html_url=html_url,
        selector=selector,
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
        "summary": summary,
        "results": results,
    }
