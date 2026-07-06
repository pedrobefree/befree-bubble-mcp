"""Runtime coverage reporting for the standalone Bubble MCP catalog."""

from __future__ import annotations

from typing import Any

from bubble_mcp.aria_dispatch import CUSTOM_RUNTIME_TOOLS, RUNTIME_TOOL_ALIASES, _load_aria_runtime_modules
from bubble_mcp.compiler.payload import (
    AUTH_WORKFLOW_ACTION_TOOLS,
    VISUAL_CREATE_TYPES,
    VISUAL_DELETE_TOOLS,
    VISUAL_UPDATE_TOOLS,
)
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.server.schemas import list_tool_schemas


NATIVE_SPECIAL_TOOLS = {
    "bubble_health_check",
    "bubble_project_bootstrap",
    "bubble_profile_add",
    "bubble_profile_list",
    "bubble_profile_status",
    "bubble_profile_cache_refresh",
    "bubble_readiness_check",
    "bubble_agent_guide",
    "bubble_tool_search",
    "bubble_task_recipe",
    "bubble_task_runbook",
    "bubble_tool_coverage",
    "bubble_catalog_quality",
    "bubble_runtime_smoke",
    "bubble_context_summary",
    "bubble_context_find",
    "bubble_context_import",
    "bubble_context_detect",
    "bubble_plan",
    "bubble_plan_dry_run",
    "bubble_eval_run",
    "bubble_eval_export_expert",
    "bubble_visual_compare",
    "bubble_visual_audit",
    "bubble_visual_capture",
    "bubble_visual_capture_actual",
    "bubble_compile_plan",
    "bubble_session_list",
    "bubble_session_inspect",
    "bubble_session_login",
    "bubble_session_import",
    "bubble_editor_write",
    "bubble_execute_plan",
    "bubble_branch_list",
    "bubble_branch_contributors",
    "bubble_changelog_fetch",
    "bubble_branch_create",
    "bubble_branch_delete",
    "bubble_extension_list",
    "bubble_extension_validate",
    "bubble_extension_import",
    "bubble_extension_enable",
    "bubble_extension_disable",
    "bubble_extension_call",
    "bubble_extension_companion_start",
    "bubble_extension_companion_status",
    "bubble_extension_companion_stop",
    "bubble_skill_validate",
    "bubble_skill_describe",
    "bubble_tool_wizard_start",
    "bubble_tool_wizard_add_capture",
    "bubble_tool_wizard_describe",
    "bubble_learning_record",
    "bubble_learning_list",
    "bubble_knowledge_refresh_source",
    "bubble_knowledge_search",
    "bubble_knowledge_fetch",
    "bubble_manual_guidance",
    "bubble_manual_context_for_tool_authoring",
    "bubble_manual_context_for_validation",
    "create_from_html",
}

COMPILER_FALLBACK_TOOLS = (
    set(VISUAL_CREATE_TYPES)
    | set(VISUAL_UPDATE_TOOLS)
    | set(VISUAL_DELETE_TOOLS)
    | set(AUTH_WORKFLOW_ACTION_TOOLS)
    | {
        "create_data_type",
        "create_data_field",
        "create_option_set",
        "create_option_attribute",
        "create_option_value",
        "create_workflow",
        "create_event",
        "add_action",
        "replace_action",
        "delete_action",
        "create_custom_state",
        "create_page",
        "delete_page",
        "create_reusable",
        "delete_reusable",
    }
)


def _runtime_methods() -> set[str]:
    bubble_cli, _bubble_sdk = _load_aria_runtime_modules()
    return {name for name in dir(bubble_cli.BubbleCLI) if not name.startswith("_")}


def _enabled_extension_tool_names() -> set[str]:
    from bubble_mcp.extensions.tools import enabled_extension_tool_schemas

    return {str(tool.get("name") or "") for tool in enabled_extension_tool_schemas()}


def classify_tool(
    name: str,
    *,
    runtime_methods: set[str] | None = None,
    extension_tool_names: set[str] | None = None,
) -> dict[str, Any]:
    """Classify one MCP tool by its primary execution path."""

    methods = runtime_methods if runtime_methods is not None else _runtime_methods()
    extension_names = extension_tool_names if extension_tool_names is not None else _enabled_extension_tool_names()
    if name in NATIVE_SPECIAL_TOOLS:
        return {"tool": name, "coverage": "native", "engine": "standalone_native"}
    if name in extension_names:
        return {"tool": name, "coverage": "extension_preview", "engine": "standalone_extension_preview"}
    if name in CUSTOM_RUNTIME_TOOLS:
        return {"tool": name, "coverage": "runtime_custom", "engine": "aria_runtime_custom"}
    alias = RUNTIME_TOOL_ALIASES.get(name)
    if alias and alias in methods:
        return {"tool": name, "coverage": "runtime_alias", "engine": "aria_runtime", "method": alias}
    if name in methods:
        return {"tool": name, "coverage": "runtime_direct", "engine": "aria_runtime", "method": name}
    if name in COMPILER_FALLBACK_TOOLS:
        return {"tool": name, "coverage": "compiler_fallback", "engine": "standalone_compiler"}
    return {"tool": name, "coverage": "uncovered", "engine": None}


def catalog_coverage_report(*, include_tools: bool = False) -> dict[str, Any]:
    """Return a compact machine-readable coverage report for all exposed tools."""

    methods = _runtime_methods()
    extension_tool_names = _enabled_extension_tool_names()
    tool_schemas = list_tool_schemas()
    tool_names = [str(tool.get("name")) for tool in tool_schemas]
    classifications = [
        classify_tool(name, runtime_methods=methods, extension_tool_names=extension_tool_names)
        for name in tool_names
    ]
    aria_names = set(ARIA_BUBBLE_TOOL_NAMES)
    aria_classifications = [item for item in classifications if item["tool"] in aria_names]
    by_coverage: dict[str, int] = {}
    for item in classifications:
        coverage = str(item["coverage"])
        by_coverage[coverage] = by_coverage.get(coverage, 0) + 1
    aria_by_coverage: dict[str, int] = {}
    for item in aria_classifications:
        coverage = str(item["coverage"])
        aria_by_coverage[coverage] = aria_by_coverage.get(coverage, 0) + 1
    uncovered = [item["tool"] for item in classifications if item["coverage"] == "uncovered"]
    aria_uncovered = [item["tool"] for item in aria_classifications if item["coverage"] == "uncovered"]
    report: dict[str, Any] = {
        "ok": not aria_uncovered,
        "tool_count": len(tool_names),
        "aria_catalog_count": len(ARIA_BUBBLE_TOOL_NAMES),
        "runtime_method_count": len(methods),
        "by_coverage": by_coverage,
        "aria_catalog": {
            "count": len(aria_classifications),
            "by_coverage": aria_by_coverage,
            "uncovered_count": len(aria_uncovered),
            "uncovered": aria_uncovered,
        },
        "uncovered_count": len(uncovered),
        "uncovered": uncovered,
    }
    if include_tools:
        report["tools"] = classifications
    return report
